import io
import tempfile
import unittest
import urllib.error
from email.message import Message
from pathlib import Path

from housing_agent.retrieval import retrieve_source, validate_official_url


class FakeResponse:
    def __init__(self, body=b'{"success":true}', status=200, content_type="application/json"):
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


if __name__ == "__main__":
    unittest.main()
