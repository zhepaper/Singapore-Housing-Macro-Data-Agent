from __future__ import annotations

import hashlib
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.message import Message
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse


OFFICIAL_HOSTS = {
    "data.gov.sg",
    "tablebuilder.singstat.gov.sg",
    "stats.mom.gov.sg",
    "www.ura.gov.sg",
    "www.mas.gov.sg",
}
RETRYABLE_HTTP_STATUSES = {429, 500, 502, 503, 504}
USER_AGENT = "Singapore-Housing-Macro-Data-Agent/0.1 (+public-data-research)"


@dataclass(frozen=True)
class RetrievalResult:
    source_id: str
    source_url: str
    retrieved_at: str
    retrieval_status: str
    http_status: int | None
    content_type: str | None
    raw_snapshot_path: str | None
    raw_file_sha256: str | None
    bytes_received: int
    retry_count: int
    error_category: str | None
    error_message: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_official_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HOSTS:
        raise ValueError(f"URL is outside the official-source allowlist: {url}")


def _content_type(headers: Message | Any) -> str | None:
    if hasattr(headers, "get_content_type"):
        return headers.get_content_type()
    value = headers.get("Content-Type") if headers else None
    return value.split(";", 1)[0].strip() if value else None


def _suffix(content_type: str | None, source_type: str) -> str:
    if content_type == "application/json" or source_type.endswith("_json"):
        return ".json"
    if content_type == "application/pdf":
        return ".pdf"
    return ".html"


def _atomic_bytes_write(path: Path, content: bytes) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)


def _retry_delay(error: urllib.error.HTTPError, attempt: int, cap: float) -> float:
    retry_after = error.headers.get("Retry-After") if error.headers else None
    if retry_after:
        try:
            return min(float(retry_after), cap)
        except ValueError:
            pass
    return min(2.0 ** attempt, cap)


def retrieve_source(
    source: dict[str, Any],
    raw_dir: Path,
    *,
    timeout: float = 30.0,
    max_retries: int = 2,
    max_retry_delay: float = 30.0,
    opener: Callable[..., Any] = urllib.request.urlopen,
    sleeper: Callable[[float], None] = time.sleep,
) -> RetrievalResult:
    source_id = source["source_id"]
    url = source["retrieval_url"]
    retrieved_at = datetime.now(timezone.utc).isoformat()
    try:
        validate_official_url(url)
    except ValueError as exc:
        return RetrievalResult(
            source_id, url, retrieved_at, "failed", None, None, None, None, 0, 0,
            "disallowed_source", str(exc),
        )

    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json,text/html;q=0.9,application/pdf;q=0.8,*/*;q=0.5",
            "User-Agent": USER_AGENT,
        },
    )
    attempts = 0
    while True:
        try:
            with opener(request, timeout=timeout) as response:
                status = int(response.status)
                content_type = _content_type(response.headers)
                body = response.read()
            path = raw_dir / f"{source_id}{_suffix(content_type, source['source_type'])}"
            _atomic_bytes_write(path, body)
            return RetrievalResult(
                source_id=source_id,
                source_url=url,
                retrieved_at=datetime.now(timezone.utc).isoformat(),
                retrieval_status="success",
                http_status=status,
                content_type=content_type,
                raw_snapshot_path=str(path),
                raw_file_sha256=hashlib.sha256(body).hexdigest(),
                bytes_received=len(body),
                retry_count=attempts,
                error_category=None,
                error_message=None,
            )
        except urllib.error.HTTPError as exc:
            error_content_type = _content_type(exc.headers)
            error_message = str(exc)
            if exc.code in RETRYABLE_HTTP_STATUSES and attempts < max_retries:
                attempts += 1
                delay = _retry_delay(exc, attempts, max_retry_delay)
                exc.close()
                sleeper(delay)
                continue
            category = "rate_limited" if exc.code == 429 else (
                "retryable_http_exhausted" if exc.code in RETRYABLE_HTTP_STATUSES else "non_retryable_http"
            )
            exc.close()
            return RetrievalResult(
                source_id, url, datetime.now(timezone.utc).isoformat(), "failed",
                exc.code, error_content_type, None, None, 0, attempts,
                category, error_message,
            )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempts < max_retries:
                attempts += 1
                sleeper(min(2.0 ** attempts, max_retry_delay))
                continue
            return RetrievalResult(
                source_id, url, datetime.now(timezone.utc).isoformat(), "failed",
                None, None, None, None, 0, attempts,
                "network_error_exhausted", str(exc),
            )


class SerialRateLimiter:
    def __init__(self, interval_seconds: float, *, clock: Callable[[], float] = time.monotonic,
                 sleeper: Callable[[float], None] = time.sleep) -> None:
        self.interval_seconds = interval_seconds
        self.clock = clock
        self.sleeper = sleeper
        self._last_request_at: float | None = None

    def wait(self) -> None:
        now = self.clock()
        if self._last_request_at is not None:
            remaining = self.interval_seconds - (now - self._last_request_at)
            if remaining > 0:
                self.sleeper(remaining)
                now = self.clock()
        self._last_request_at = now


def retrieve_catalog_sources(
    sources: list[dict[str, Any]],
    raw_dir: Path,
    *,
    request_interval_seconds: float = 13.0,
    timeout: float = 30.0,
    max_retries: int = 2,
) -> list[RetrievalResult]:
    limiter = SerialRateLimiter(request_interval_seconds)
    results: list[RetrievalResult] = []
    for source in sources:
        limiter.wait()
        results.append(retrieve_source(
            source,
            raw_dir,
            timeout=timeout,
            max_retries=max_retries,
        ))
    return results
