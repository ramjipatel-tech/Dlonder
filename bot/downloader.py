import asyncio
import ipaddress
import mimetypes
import re
import socket
import time
from pathlib import Path
from urllib.parse import urlparse, unquote

import aiohttp

VIDEO_TYPES = {".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi", ".ts"}
_CD_FILENAME_RE = re.compile(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';\r\n]+)', re.I)


def _is_public_ip(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped:
        return ip_obj.ipv4_mapped.is_global
    return ip_obj.is_global


def _is_public_host(host: str) -> bool:
    try:
        return _is_public_ip(ipaddress.ip_address(host))
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
            return bool(infos) and all(_is_public_ip(ipaddress.ip_address(x[4][0])) for x in infos)
        except Exception:
            return False


def validate_url(url: str, allowed_hosts: set[str]) -> str:
    p = urlparse(url.strip())
    if p.scheme != "https" or not p.hostname:
        raise ValueError("Please send a valid HTTPS direct video URL.")
    host = p.hostname.lower()
    if not _is_public_host(host):
        raise ValueError("This host is not publicly reachable.")
    if allowed_hosts and not any(host == h or host.endswith("." + h) for h in allowed_hosts):
        raise ValueError("This domain is not in ALLOWED_HOSTS.")
    return url.strip()


def _extract_filename(final_url: str, content_disposition: str, suggested_name: str | None) -> str:
    if content_disposition:
        m = _CD_FILENAME_RE.search(content_disposition)
        if m and m.group(1).strip():
            return unquote(Path(m.group(1).strip()).name)
    url_name = unquote(Path(urlparse(final_url).path).name)
    if url_name and Path(url_name).suffix.lower() in VIDEO_TYPES:
        return url_name
    if suggested_name:
        return Path(suggested_name.strip()).name
    return url_name or "video.mp4"


async def download_direct_video(
    url: str,
    dest_dir: Path,
    max_bytes: int,
    headers: dict | None = None,
    suggested_name: str | None = None,
) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    timeout = aiohttp.ClientTimeout(total=900, connect=25, sock_read=90)
    async with aiohttp.ClientSession(timeout=timeout, headers=headers or {"User-Agent": "PersonalVideoBot/1.0"}) as session:
        async with session.get(url, allow_redirects=True) as resp:
            resp.raise_for_status()
            final = urlparse(str(resp.url))
            if final.scheme != "https" or not final.hostname or not _is_public_host(final.hostname):
                raise ValueError("Redirect target is not allowed.")
            content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
            length = int(resp.headers.get("Content-Length", "0") or 0)
            if length and length > max_bytes:
                raise ValueError(f"File is larger than the configured limit ({max_bytes // (1024 * 1024)} MB).")

            name = _extract_filename(str(resp.url), resp.headers.get("Content-Disposition", ""), suggested_name)
            suffix = Path(name).suffix.lower()
            is_video_ct = content_type.startswith("video/")
            is_binary_video = content_type in ("application/octet-stream", "binary/octet-stream", "") and (
                suffix in VIDEO_TYPES or bool(suggested_name and Path(suggested_name).suffix.lower() in VIDEO_TYPES)
            )
            if suffix not in VIDEO_TYPES and not is_video_ct and not is_binary_video:
                raise ValueError("This is not a direct video file URL. Use the service's official download/export option.")
            if suffix not in VIDEO_TYPES:
                guessed = mimetypes.guess_extension(content_type) or ".mp4"
                name += guessed if guessed in VIDEO_TYPES else ".mp4"

            safe_name = "".join(c for c in name if c.isalnum() or c in "._-")[:100] or "video.mp4"
            target = dest_dir / f"{time.time_ns()}_{safe_name}"
            total = 0
            try:
                with target.open("wb") as f:
                    async for chunk in resp.content.iter_chunked(1024 * 1024):
                        total += len(chunk)
                        if total > max_bytes:
                            raise ValueError("File exceeded the configured size limit while downloading.")
                        f.write(chunk)
            except Exception:
                target.unlink(missing_ok=True)
                raise
    return target
