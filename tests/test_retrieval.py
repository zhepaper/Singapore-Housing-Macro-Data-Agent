import io
import json
import tempfile
import unittest
import urllib.error
from email.message import Message
from pathlib import Path

from housing_agent.retrieval import (
    RetrievalResult,
    retrieve_source,
    use_approved_cached_fallback,
    validate_official_url,
)


class FakeResponse:
    def __init__(self, body=None, status=200, content_type="application/json"):
        if body is None:
            body = json.dumps({
                "success": True,
                "result": {"records": [{"_id": 1}], "total": 1, "limit": 100,
                           "_links": {"next": "/api/action/example?offset=100"}},
            }).encode()
        self.body = body
        self.status = status
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            "source_id": "test_source",
            "source_type": "datagov_json",
            "retrieval_url": "https://data.gov.sg/api/action/example",
        }

    def test_rejects_non_official_source(self):
        with self.assertRaises(ValueError):
            validate_official_url("https://example.com/data.json")

    def test_success_writes_checksum_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = retrieve_source(
                self.source, Path(temporary), opener=lambda request, timeout: FakeResponse()
            )
            self.assertEqual(result.retrieval_status, "success")
            self.assertEqual(len(result.raw_file_sha256), 64)
            self.assertTrue(Path(result.raw_snapshot_path).is_file())

    def test_retryable_error_retries_then_succeeds(self):
        calls = []
        sleeps = []
        headers = Message()
        headers["Retry-After"] = "2"

        def opener(request, timeout):
            calls.append(request.full_url)
            if len(calls) == 1:
                raise urllib.error.HTTPError(
                    request.full_url, 503, "unavailable", headers, io.BytesIO(b"temporary")
                )
            return FakeResponse()

        with tempfile.TemporaryDirectory() as temporary:
            result = retrieve_source(
                self.source, Path(temporary), opener=opener, sleeper=sleeps.append
            )
        self.assertEqual(result.retrieval_status, "success")
        self.assertEqual(result.retry_count, 1)
        self.assertEqual(sleeps, [2.0])

    def test_429_honours_retry_after(self):
        calls = []
        sleeps = []
        headers = Message()
        headers["Retry-After"] = "7"

        def opener(request, timeout):
            calls.append(request.full_url)
            if len(calls) == 1:
                raise urllib.error.HTTPError(
                    request.full_url, 429, "rate limited", headers, io.BytesIO(b"slow down")
                )
            return FakeResponse()

        with tempfile.TemporaryDirectory() as temporary:
            result = retrieve_source(
                self.source, Path(temporary), opener=opener, sleeper=sleeps.append
            )
        self.assertEqual(result.retrieval_status, "success")
        self.assertEqual(result.retry_count, 1)
        self.assertEqual(sleeps, [7.0])

    def test_timeout_retries_are_bounded(self):
        calls = []
        sleeps = []

        def opener(request, timeout):
            calls.append(timeout)
            raise TimeoutError("read timed out")

        with tempfile.TemporaryDirectory() as temporary:
            result = retrieve_source(
                self.source, Path(temporary), opener=opener, sleeper=sleeps.append,
                timeout=4.0, max_retries=2,
            )
        self.assertEqual(result.retrieval_status, "failed")
        self.assertEqual(result.error_category, "network_error_exhausted")
        self.assertEqual(result.retry_count, 2)
        self.assertEqual(calls, [4.0, 4.0, 4.0])
        self.assertEqual(sleeps, [2.0, 4.0])

    def test_non_retryable_error_fails_once(self):
        headers = Message()

        def opener(request, timeout):
            raise urllib.error.HTTPError(
                request.full_url, 404, "not found", headers, io.BytesIO(b"missing")
            )

        with tempfile.TemporaryDirectory() as temporary:
            result = retrieve_source(
                self.source, Path(temporary), opener=opener, sleeper=lambda seconds: None
            )
        self.assertEqual(result.error_category, "non_retryable_http")
        self.assertEqual(result.retry_count, 0)

    def test_datagov_pagination_preserves_pages_and_combines_records(self):
        first = {
            "success": True,
            "result": {
                "records": [{"_id": 1}], "total": 2, "limit": 1,
                "_links": {"next": "/api/action/example?offset=1&limit=1"},
            },
        }
        second = {
            "success": True,
            "result": {
                "records": [{"_id": 2}], "total": 2, "limit": 1,
                "_links": {"next": "/api/action/example?offset=2&limit=1"},
            },
        }

        def opener(request, timeout):
            body = second if "offset=1" in request.full_url else first
            return FakeResponse(json.dumps(body).encode())

        with tempfile.TemporaryDirectory() as temporary:
            result = retrieve_source(self.source, Path(temporary), opener=opener)
            combined = json.loads(Path(result.raw_snapshot_path).read_text())
            self.assertEqual([row["_id"] for row in combined["result"]["records"]], [1, 2])
            self.assertEqual(len(result.raw_page_paths), 2)
            self.assertTrue(all(Path(path).is_file() for path in result.raw_page_paths))

    def test_malformed_datagov_response_is_schema_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = retrieve_source(
                self.source,
                Path(temporary),
                opener=lambda request, timeout: FakeResponse(b'{"success":true}'),
            )
        self.assertEqual(result.retrieval_status, "failed")
        self.assertEqual(result.error_category, "schema_error")

    def test_approved_cache_fallback_is_explicit_and_copied(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cached = root / "data/raw/spike_1"
            cached.mkdir(parents=True)
            (cached / "test_source.json").write_text('{"cached":true}')
            run_raw = root / "runs/run/raw"
            run_raw.mkdir(parents=True)
            failed = RetrievalResult(
                "test_source", self.source["retrieval_url"], "2026-10-01T00:00:00+00:00",
                "failed", 403, "text/html", None, None, [], [], 0, 0,
                "non_retryable_http", "HTTP 403",
            )
            result = use_approved_cached_fallback(
                failed, self.source, project_root=root, run_raw_dir=run_raw
            )
            self.assertEqual(result.retrieval_status, "fallback")
            self.assertIn("cached_fallback_after", result.error_category)
            self.assertTrue(Path(result.raw_snapshot_path).is_file())


if __name__ == "__main__":
    unittest.main()
