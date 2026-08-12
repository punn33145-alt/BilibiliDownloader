"""yt-dlp video download service — Module 1 (no AI)."""

from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Optional

import yt_dlp
from yt_dlp.utils import DownloadError, ExtractorError

from app.core.ffmpeg import find_ffmpeg
from app.core.paths import get_bbdown_path, sanitize_filename
from app.core.ssl_setup import configure_ssl_certificates, get_ca_bundle_path
from app.core.url_validator import normalize_bilibili_url
from app.downloader.assets import save_thumbnail
from app.downloader.metadata import write_readme
from app.downloader.models import DownloadProgress, DownloadResult, VideoInfo

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[DownloadProgress], None]


class DownloadService:
    """Download Bilibili videos, subtitles, thumbnail, and README."""

    def __init__(self) -> None:
        self._cancel_requested = False

    def request_cancel(self) -> None:
        self._cancel_requested = True

    def reset_cancel(self) -> None:
        self._cancel_requested = False

    @staticmethod
    def _base_options() -> dict[str, Any]:
        configure_ssl_certificates()
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "retries": 3,
            "fragment_retries": 3,
            "socket_timeout": 30,
            "geo_bypass": True,
        }
        ffmpeg = find_ffmpeg()
        if ffmpeg:
            opts["ffmpeg_location"] = str(Path(ffmpeg).parent)
        ca = get_ca_bundle_path()
        if ca:
            opts["ca_certs"] = ca
        return opts

    def fetch_video_info(self, url: str) -> VideoInfo:
        normalized = normalize_bilibili_url(url)
        if not normalized:
            raise ValueError("Invalid Bilibili URL.")

        options = {**self._base_options(), "skip_download": True}
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(normalized, download=False)
        except ExtractorError as exc:
            raise self._map_extractor_error(exc) from exc
        except DownloadError as exc:
            raise self._map_download_error(exc) from exc

        if not info:
            raise RuntimeError("Video unavailable.")

        return VideoInfo(
            url=normalized,
            title=info.get("title") or "Unknown Title",
            duration=int(info.get("duration") or 0),
            thumbnail_url=info.get("thumbnail") or "",
            uploader=info.get("uploader"),
            video_id=info.get("id"),
            raw_info=dict(info),
        )

    def download(
        self,
        url: str,
        save_root: str,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> DownloadResult:
        self.reset_cancel()
        normalized = normalize_bilibili_url(url)
        if not normalized:
            raise ValueError("Invalid Bilibili URL.")

        save_path = Path(save_root)
        if not save_path.exists():
            raise ValueError("Save folder does not exist.")
        if not os.access(save_path, os.W_OK):
            raise PermissionError("Cannot write to the selected folder.")
        if not find_ffmpeg():
            raise RuntimeError(
                "FFmpeg not found on PATH. Install FFmpeg and restart."
            )

        # Fetch metadata first to determine folder name
        options = {**self._base_options(), "skip_download": True}
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(normalized, download=False)

        title = info.get("title") or "video"
        safe_title = sanitize_filename(title)
        video_folder = save_path / safe_title
        video_folder.mkdir(parents=True, exist_ok=True)

        video_file = video_folder / f"{safe_title}.mp4"
        outtmpl = str(video_folder / f"{safe_title}.%(ext)s")

        # Optional: if BBDown is configured (see get_bbdown_path), try it
        # first — it can fetch Bilibili's TV-API stream, which doesn't have
        # the web/app API's baked-in logo watermark. Any failure here
        # (not configured, not logged in, network error, binary missing)
        # falls straight through to the normal yt-dlp download below —
        # this is purely an optional enhancement, never a hard dependency.
        bbdown_path = get_bbdown_path()
        if bbdown_path is not None:
            bbdown_file = self._download_with_bbdown(
                bbdown_path, normalized, video_folder, progress_callback
            )
            if bbdown_file is not None:
                video_file = bbdown_file
                thumb_path = save_thumbnail(
                    info.get("thumbnail") or "",
                    video_folder / "Thumbnail.jpg",
                )
                readme_path = video_folder / "README.txt"
                write_readme(readme_path, info, normalized)
                return DownloadResult(
                    output_dir=video_folder,
                    video_path=video_file,
                    readme_path=readme_path,
                    thumbnail_path=thumb_path,
                    subtitle_path=None,
                )
            logger.info("BBDown unavailable/failed; falling back to yt-dlp.")

        ydl_opts: dict[str, Any] = {
            **self._base_options(),
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "outtmpl": outtmpl,
            "progress_hooks": [self._make_hook(progress_callback)],
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(normalized, download=True)
                if not video_file.exists():
                    prepared = Path(ydl.prepare_filename(info))
                    mp4 = prepared.with_suffix(".mp4")
                    if mp4.exists():
                        video_file = mp4
                    elif prepared.exists():
                        video_file = prepared

            thumb_path = save_thumbnail(
                info.get("thumbnail") or "",
                video_folder / "Thumbnail.jpg",
            )
            readme_path = video_folder / "README.txt"
            write_readme(readme_path, info, normalized)

            return DownloadResult(
                output_dir=video_folder,
                video_path=video_file,
                readme_path=readme_path,
                thumbnail_path=thumb_path,
                subtitle_path=None,
            )
        except DownloadError as exc:
            if self._cancel_requested:
                raise RuntimeError("Download cancelled.") from exc
            raise self._map_download_error(exc) from exc
        except ExtractorError as exc:
            raise self._map_extractor_error(exc) from exc

    @staticmethod
    def _parse_bbdown_percentage(line: str) -> Optional[float]:
        """
        Best-effort extraction of a progress percentage from a line of
        BBDown output. Looks for any "NN.NN%" / "NN%" pattern rather than
        depending on BBDown's exact log wording/language, so it keeps
        working even if that wording changes across versions.
        """
        match = re.search(r"(\d{1,3}(?:\.\d+)?)\s*%", line)
        if not match:
            return None
        try:
            value = float(match.group(1))
        except ValueError:
            return None
        return max(0.0, min(100.0, value))

    def _download_with_bbdown(
        self,
        bbdown_path: Path,
        url: str,
        video_folder: Path,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Optional[Path]:
        """
        Try downloading via BBDown's TV-API mode (-tv), which avoids the
        watermark baked into Bilibili's normal web/app API stream. Returns
        the downloaded mp4's path on success, or None on any failure —
        callers should fall back to the standard yt-dlp download.

        Requires the user to have run `BBDown logintv` once beforehand
        (interactive QR-code login); BBDown persists that login itself, so
        no credentials are handled here.
        """
        video_extensions = ("*.mp4", "*.mkv", "*.flv", "*.ts", "*.m4s")
        existing_before = {
            f"{p.parent}/{p.name}"
            for ext in video_extensions
            for p in video_folder.rglob(ext)
        }

        try:
            if progress_callback:
                progress_callback(
                    DownloadProgress(
                        status="downloading",
                        percentage=0.0,
                        message="Downloading via BBDown (TV API, no watermark)...",
                    )
                )
            # Popen + line-by-line reading (instead of subprocess.run's
            # capture_output, which blocks silently until the whole
            # process exits) lets us relay BBDown's own progress output
            # to the UI as it happens — otherwise the progress bar sits
            # frozen at 0% for the entire download even though BBDown is
            # actively working (visible only indirectly via the temp
            # segment files it creates while multi-thread downloading,
            # which is on by default).
            process = subprocess.Popen(
                [str(bbdown_path), url, "-tv"],
                cwd=str(video_folder),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )

            output_lines: list[str] = []
            start_time = time.monotonic()
            timeout_seconds = 600

            assert process.stdout is not None
            for line in process.stdout:
                output_lines.append(line)
                if progress_callback:
                    pct = self._parse_bbdown_percentage(line)
                    if pct is not None:
                        progress_callback(
                            DownloadProgress(
                                status="downloading",
                                percentage=pct,
                                message="Downloading via BBDown (TV API, no watermark)...",
                            )
                        )
                if time.monotonic() - start_time > timeout_seconds:
                    process.kill()
                    logger.warning(
                        "BBDown timed out after %ds (possibly stuck waiting "
                        "on login/input) — falling back to yt-dlp.",
                        timeout_seconds,
                    )
                    return None

            returncode = process.wait(timeout=30)
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("BBDown failed to run: %s", exc)
            return None

        if returncode != 0:
            logger.warning(
                "BBDown exited with code %s: %s",
                returncode,
                "".join(output_lines).strip()[-500:],
            )
            return None

        # BBDown may nest output in a subfolder and/or use a container
        # extension other than .mp4 depending on codec/muxing (e.g. .mkv).
        # Search recursively across common video extensions rather than
        # only *.mp4 directly in video_folder, or a successful download
        # can be missed and silently treated as a failure.
        new_videos = [
            p
            for ext in video_extensions
            for p in video_folder.rglob(ext)
            if f"{p.parent}/{p.name}" not in existing_before
        ]
        if not new_videos:
            logger.warning("BBDown reported success but no new video file was found.")
            return None

        return max(new_videos, key=lambda p: p.stat().st_mtime)

    def _make_hook(self, callback: Optional[ProgressCallback]):
        def hook(data: dict[str, Any]) -> None:
            if self._cancel_requested:
                raise DownloadError("Download cancelled.")
            if callback:
                callback(self._parse_progress(data))

        return hook

    @staticmethod
    def _parse_progress(data: dict[str, Any]) -> DownloadProgress:
        status = data.get("status", "")
        downloaded = int(data.get("downloaded_bytes") or 0)
        total = data.get("total_bytes") or data.get("total_bytes_estimate")
        total_int = int(total) if total else None
        speed = data.get("speed")
        eta = data.get("eta")

        pct = 0.0
        if total_int and total_int > 0:
            pct = min(100.0, downloaded / total_int * 100.0)
        elif status == "finished":
            pct = 100.0

        if status == "downloading":
            msg = (
                f"Downloading... {DownloadProgress.format_bytes(downloaded)}"
                f" / {DownloadProgress.format_bytes(total_int or 0)}"
                f" | {DownloadProgress.format_speed(speed)}"
                f" | ETA {DownloadProgress.format_eta(eta)}"
            )
        elif status == "finished":
            msg = "Processing..."
        else:
            msg = status.capitalize() if status else "Working..."

        return DownloadProgress(status=status, percentage=pct, message=msg)

    @staticmethod
    def _map_extractor_error(exc: ExtractorError) -> RuntimeError:
        text = str(exc).lower()
        if "private" in text or "login" in text:
            return RuntimeError("Video is private or requires login.")
        if "geo" in text or "region" in text or "blocked" in text:
            return RuntimeError("Video is blocked in your region.")
        if "unavailable" in text or "removed" in text:
            return RuntimeError("Video unavailable.")
        return RuntimeError(f"Could not access video: {exc}")

    @staticmethod
    def _map_download_error(exc: DownloadError) -> RuntimeError:
        text = str(exc).lower()
        if "certificate" in text or "ssl" in text:
            return RuntimeError(
                "SSL certificate error. Run: pip install truststore certifi"
            )
        if "network" in text or "connection" in text:
            return RuntimeError("Network error. Check your connection.")
        if "ffmpeg" in text:
            return RuntimeError("FFmpeg error during merge.")
        if "no space" in text:
            return RuntimeError("Disk full.")
        if "permission" in text:
            return RuntimeError("Permission denied.")
        return RuntimeError(f"Download failed: {exc}")
