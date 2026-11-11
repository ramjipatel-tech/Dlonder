import asyncio
import ipaddress
import mimetypes
import socket
from pathlib import Path
from urllib.parse import urlparse, unquote

import aiohttp

VIDEO_TYPES = {".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi"}

def _is_public_host(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_global
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
            return all(ipaddress.ip_address(x[4][0]).is_global for x in infos)
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

async def download_direct_video(url: str, dest_dir: Path, max_bytes: int, headers: dict | None = None) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    timeout = aiohttp.ClientTimeout(total=900, connect=25, sock_read=90)
    async with aiohttp.ClientSession(timeout=timeout, headers=headers or {"User-Agent": "PersonalVideoBot/1.0"}) as session:
        async with session.get(url, allow_redirects=True) as resp:
            resp.raise_for_status()
            final = urlparse(str(resp.url))
            if final.scheme != "https" or not final.hostname or not _is_public_host(final.hostname):
                raise ValueError("Redirect target is not allowed.")
            validate_url(str(resp.url), set())
            content_type = resp.headers.get("Content-Type", "").split(";")[0].lower()
            length = int(resp.headers.get("Content-Length", "0") or 0)
            if length and length > max_bytes:
                raise ValueError(f"File is larger than the configured limit ({max_bytes // (1024*1024)} MB).")
            name = unquote(Path(final.path).name) or "video"
            suffix = Path(name).suffix.lower()
            if suffix not in VIDEO_TYPES and not content_type.startswith("video/"):
                raise ValueError("This is not a direct video file URL. Use the service's official download/export option.")
            if suffix not in VIDEO_TYPES:
                name += mimetypes.guess_extension(content_type) or ".mp4"
            safe_name = "".join(c for c in name if c.isalnum() or c in "._-")[:100] or "video.mp4"
            target = dest_dir / f"{asyncio.get_running_loop().time_ns()}_{safe_name}"
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
