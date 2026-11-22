"""Reusable helpers for processing audio asset previews."""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse

from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH, override=False)
else:
    load_dotenv(override=False)

from processing.providers import get_adapter, PreviewAdapterError, PreviewFetchResult

logger = logging.getLogger(__name__)

DEFAULT_PREVIEW_DURATION_SECONDS = 0
MIN_PREVIEW_DURATION_SECONDS = 30
MAX_PREVIEW_DURATION_SECONDS = 60
_FFMPEG_PATH = shutil.which("ffmpeg")
_FFMPEG_WARNING_EMITTED = False


def _coerce_preview_duration(raw_value: Optional[str]) -> Optional[int]:
    """Normalise preview duration env input into the 30–60 s window."""
    value_str = (raw_value or str(DEFAULT_PREVIEW_DURATION_SECONDS)).strip()
    try:
        parsed = int(value_str)
    except ValueError:
        logger.warning(
            "Invalid COBALT_PREVIEW_DURATION_SECONDS=%r; reverting to %s seconds",
            raw_value,
            DEFAULT_PREVIEW_DURATION_SECONDS,
        )
        parsed = DEFAULT_PREVIEW_DURATION_SECONDS
    if parsed <= 0:
        return None
    return max(MIN_PREVIEW_DURATION_SECONDS, min(MAX_PREVIEW_DURATION_SECONDS, parsed))


TARGET_PREVIEW_DURATION = _coerce_preview_duration(os.getenv("COBALT_PREVIEW_DURATION_SECONDS"))

STORAGE_MODE = os.getenv("AUDIO_STORAGE_MODE", "local")
LOCAL_STORAGE_ROOT = Path(os.getenv("AUDIO_STORAGE_ROOT", "storage/audio_previews"))
S3_BUCKET = os.getenv("AUDIO_STORAGE_S3_BUCKET")
S3_REGION = os.getenv("AUDIO_STORAGE_S3_REGION")
GCS_BUCKET = os.getenv("GCS_BUCKET")
GCP_CREDENTIALS_PATH = os.getenv("GCP_CREDENTIALS_PATH")
FETCH_LIMIT = int(os.getenv("AUDIO_ASSET_FETCH_LIMIT", 10))
MAX_ATTEMPTS = int(os.getenv("AUDIO_ASSET_MAX_ATTEMPTS", 5))
DOWNLOAD_TIMEOUT = int(os.getenv("AUDIO_PREVIEW_DOWNLOAD_TIMEOUT", 300))
CONNECT_TIMEOUT = int(os.getenv("AUDIO_PREVIEW_CONNECT_TIMEOUT", 15))
DEFAULT_DOWNLOAD_HEADERS = {
    "User-Agent": os.getenv(
        "AUDIO_PREVIEW_USER_AGENT",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    ),
    "Accept": os.getenv(
        "AUDIO_PREVIEW_ACCEPT_HEADER",
        "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    ),
    "Accept-Language": os.getenv("AUDIO_PREVIEW_ACCEPT_LANGUAGE", "en-US,en;q=0.9"),
}


class PreviewDownloadError(RuntimeError):
    """Raised when the preview download request fails."""

    def __init__(self, *, status_code: int, host: Optional[str], message: str):
        super().__init__(message)
        self.status_code = status_code
        self.host = host


class StorageClient:
    """Storage abstraction (local disk or S3)."""

    def __init__(self) -> None:
        if STORAGE_MODE == "local":
            LOCAL_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
            self._mode = "local"
        elif STORAGE_MODE == "s3":
            try:
                import boto3  # type: ignore

                self._mode = "s3"
                self._s3 = boto3.client("s3", region_name=S3_REGION)
            except Exception as exc:  # pragma: no cover - optional path
                raise RuntimeError(f"Failed to initialise S3 client: {exc}") from exc
        elif STORAGE_MODE == "gcs":
            try:
                from google.cloud import storage as gcs_storage  # type: ignore

                resolved_path = _resolve_secret_path(GCP_CREDENTIALS_PATH)
                if not GCS_BUCKET or not resolved_path:
                    raise RuntimeError("Set GCS_BUCKET and GCP_CREDENTIALS_PATH for GCS storage mode")
                self._mode = "gcs"
                self._gcs_client = gcs_storage.Client.from_service_account_json(str(resolved_path))
                self._gcs_bucket = self._gcs_client.bucket(GCS_BUCKET)
            except Exception as exc:  # pragma: no cover - optional path
                raise RuntimeError(f"Failed to initialise GCS client: {exc}") from exc
        else:
            raise RuntimeError(f"Unsupported AUDIO_STORAGE_MODE '{STORAGE_MODE}'")

    def save(self, *, provider_type: str, provider_track_id: str, file_extension: str, data: bytes) -> str:
        if self._mode == "local":
            filename = f"{provider_track_id}{file_extension}"
            provider_dir = LOCAL_STORAGE_ROOT / provider_type
            provider_dir.mkdir(parents=True, exist_ok=True)
            destination = provider_dir / filename
            destination.write_bytes(data)
            return str(destination.resolve())

        if self._mode == "s3":
            key = f"{provider_type}/{provider_track_id}{file_extension}"
            self._s3.put_object(Bucket=S3_BUCKET, Key=key, Body=data)  # type: ignore[attr-defined]
            return f"s3://{S3_BUCKET}/{key}"

        # GCS path
        key = f"{provider_type}/{provider_track_id}{file_extension}"
        blob = self._gcs_bucket.blob(key)  # type: ignore[attr-defined]
        content_type = _guess_content_type(file_extension)
        blob.upload_from_string(data, content_type=content_type)
        return f"gs://{GCS_BUCKET}/{key}"


def fetch_pending_assets(conn) -> list[dict]:
    """Return audio assets that still need preview caching."""
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT *
            FROM audio_assets
            WHERE deleted_at IS NULL
              AND (storage_path IS NULL OR fetch_status = 'failed')
              AND fetch_attempts < %s
            ORDER BY created_at ASC
            LIMIT %s
            """,
            (MAX_ATTEMPTS, FETCH_LIMIT),
        )
        return cursor.fetchall()


def _update_success(cursor, asset_id: str, *, storage_path: str, checksum: str, attempts: int, result: PreviewFetchResult) -> None:
    now = datetime.now(timezone.utc)
    cursor.execute(
        """
        UPDATE audio_assets
        SET storage_path = %s,
            storage_checksum = %s,
            fetch_status = 'fetched',
            fetched_at = %s,
            last_checked_at = %s,
            fetch_attempts = %s,
            license_name = COALESCE(%s, license_name),
            license_url = COALESCE(%s, license_url),
            license_notes = COALESCE(%s, license_notes),
            fetch_error = NULL
        WHERE id = %s
        """,
        (
            storage_path,
            checksum,
            now,
            now,
            attempts,
            result.license_name,
            result.license_url,
            result.license_notes,
            asset_id,
        ),
    )


def _update_failure(cursor, asset_id: str, *, attempts: int, error: str) -> None:
    now = datetime.now(timezone.utc)
    cursor.execute(
        """
        UPDATE audio_assets
        SET fetch_status = 'failed',
            fetch_attempts = %s,
            fetch_error = %s,
            last_checked_at = %s
        WHERE id = %s
        """,
        (attempts, error[:500], now, asset_id),
    )


def _build_download_headers(fetch_result: PreviewFetchResult) -> dict:
    headers = dict(DEFAULT_DOWNLOAD_HEADERS)
    if fetch_result.headers:
        headers.update(fetch_result.headers)
    if "Referer" not in headers:
        try:
            parsed = urlparse(fetch_result.download_url)
            if parsed.scheme and parsed.netloc:
                headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
        except ValueError:
            pass
    return headers


def _guess_content_type(file_extension: str) -> str:
    if file_extension.endswith(".mp3"):
        return "audio/mpeg"
    if file_extension.endswith(".webm"):
        return "audio/webm"
    return "audio/mp4"


def _trim_preview_duration(data: bytes, *, file_extension: str) -> bytes:
    """Trim downloaded previews to the configured duration via ffmpeg."""
    if not TARGET_PREVIEW_DURATION:
        return data

    ffmpeg_path = _FFMPEG_PATH
    if not ffmpeg_path:
        global _FFMPEG_WARNING_EMITTED
        if not _FFMPEG_WARNING_EMITTED:
            logger.warning(
                "ffmpeg binary not found; skipping COBALT_PREVIEW_DURATION_SECONDS enforcement.",
            )
            _FFMPEG_WARNING_EMITTED = True
        return data

    suffix = file_extension or ".mp3"
    if not suffix.startswith("."):
        suffix = f".{suffix}"

    input_path: Optional[str] = None
    output_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as input_file:
            input_file.write(data)
            input_path = input_file.name
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as output_file:
            output_path = output_file.name

        subprocess.run(
            [
                ffmpeg_path,
                "-y",
                "-i",
                input_path,
                "-t",
                str(TARGET_PREVIEW_DURATION),
                "-acodec",
                "copy",
                output_path,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        trimmed_data = Path(output_path).read_bytes()
        if trimmed_data:
            return trimmed_data
    except subprocess.CalledProcessError as exc:
        logger.warning(
            "ffmpeg trim failed for preview (target=%ss): %s",
            TARGET_PREVIEW_DURATION,
            exc,
        )
    finally:
        for tmp_path in (input_path, output_path):
            if not tmp_path:
                continue
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
    return data


def _download_preview(fetch_result: PreviewFetchResult) -> Tuple[bytes, str]:
    if fetch_result.local_file_path:
        path = Path(fetch_result.local_file_path)
        if not path.exists():
            raise RuntimeError(f"Local preview file {path} does not exist")
        data = path.read_bytes()
        suffix = path.suffix or fetch_result.file_extension or ".mp3"
        data = _trim_preview_duration(data, file_extension=suffix)
        checksum = hashlib.sha256(data).hexdigest()
        if fetch_result.cleanup_local_file:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        return data, checksum

    if not fetch_result.download_url:
        raise RuntimeError("No download URL available for preview fetch result")

    try:
        headers = _build_download_headers(fetch_result)
        parsed_url = urlparse(fetch_result.download_url)
        host = parsed_url.netloc.lower() if parsed_url.netloc else None
        response = requests.get(
            fetch_result.download_url,
            stream=True,
            timeout=(CONNECT_TIMEOUT, DOWNLOAD_TIMEOUT),
            headers=headers,
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Download request failed: {exc}") from exc
    if response.status_code != 200:
        raise PreviewDownloadError(
            status_code=response.status_code,
            host=host,
            message=f"Download failed with status {response.status_code}",
        )

    content_type = (response.headers.get("Content-Type") or "").lower()
    if content_type and not (
        content_type.startswith("audio/")
        or content_type.startswith("video/")
        or content_type.startswith("application/octet-stream")
    ):
        raise RuntimeError(f"Unexpected content type '{content_type}' while downloading preview")

    chunks = []
    for chunk in response.iter_content(chunk_size=8192):
        if not chunk:
            continue
        chunks.append(chunk)

    data = b"".join(chunks)
    sample = data[:200].lstrip()
    if sample.startswith(b"<!DOCTYPE") or sample.startswith(b"<html"):
        raise RuntimeError("Preview download returned HTML instead of audio data")
    if not data:
        raise RuntimeError("Preview download returned an empty body")

    file_extension = fetch_result.file_extension or ".mp3"
    data = _trim_preview_duration(data, file_extension=file_extension)
    checksum = hashlib.sha256(data).hexdigest()
    return data, checksum


def process_audio_asset(conn, asset_id: str, *, storage: Optional[StorageClient] = None, commit: bool = True) -> dict:
    """Fetch and store the preview for a single audio asset.

    Returns a dict containing the updated storage path & checksum when successful.
    """
    storage = storage or StorageClient()
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("SELECT * FROM audio_assets WHERE id = %s FOR UPDATE", (asset_id,))
        asset = cursor.fetchone()
        if not asset:
            raise ValueError(f"Audio asset {asset_id} not found")

        attempts = int(asset.get("fetch_attempts") or 0) + 1

        provider_type = asset["provider_type"]
        logger.info("Processing audio asset %s (%s)", asset_id, provider_type)

        try:
            adapter = get_adapter(provider_type)
            result = adapter.resolve(
                source_url=asset["source_url"],
                preview_url=asset.get("provider_preview_url"),
                provider_track_id=asset.get("provider_track_id"),
            )
            data, checksum = _download_preview(result)
            storage_path = storage.save(
                provider_type=provider_type,
                provider_track_id=result.provider_track_id,
                file_extension=result.file_extension,
                data=data,
            )
            _update_success(cursor, asset_id, storage_path=storage_path, checksum=checksum, attempts=attempts, result=result)
            if commit:
                conn.commit()
            return {"storage_path": storage_path, "checksum": checksum}
        except PreviewDownloadError as exc:
            logger.warning(
                "preview_download_failed provider=%s asset=%s status=%s host=%s",
                provider_type,
                asset_id,
                exc.status_code,
                exc.host or "unknown",
            )
            _update_failure(cursor, asset_id, attempts=attempts, error=str(exc))
            if commit:
                conn.commit()
            raise
        except PreviewAdapterError as exc:
            logger.error("Adapter error for asset %s: %s", asset_id, exc)
            _update_failure(cursor, asset_id, attempts=attempts, error=str(exc))
            if commit:
                conn.commit()
            raise
        except Exception as exc:  # pragma: no cover
            logger.exception("Unexpected failure processing asset %s", asset_id)
            _update_failure(cursor, asset_id, attempts=attempts, error=str(exc))
            if commit:
                conn.commit()
            raise


__all__ = [
    "StorageClient",
    "fetch_pending_assets",
    "process_audio_asset",
    "MAX_ATTEMPTS",
    "FETCH_LIMIT",
]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
def _resolve_secret_path(raw_path: Optional[str]) -> Optional[Path]:
    if not raw_path:
        return None
    path = Path(raw_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path
