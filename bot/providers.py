import re
from urllib.parse import urlparse, parse_qsl, unquote, urljoin
import aiohttp
from .config import DISKWALA_RESOLVER_URL, TERABOX_COOKIE
from .downloader import validate_url

VIDEO_EXTS = (".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi", ".ts")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0 Safari/537.36"
DISKWALA_DOMAINS = ("diskwala.com", "diskwala.app", "diskwala.in", "diskwala.org", "diskwala.net")
DEFAULT_DISKWALA_API = "https://mini.thediskwala.com/api/fetch-video"
TERABOX_HINTS = (
    "terabox", "1024tera", "nephobox", "freeterabox", "mirrobox",
    "dubox", "4funbox", "momerybox", "tibibox", "terashare",
)


def provider_for(url: str) -> str | None:
    host = (urlparse(url).hostname or "").lower()
    if any(host == d or host.endswith("." + d) for d in DISKWALA_DOMAINS):
        return "diskwala"
    if any(x in host for x in TERABOX_HINTS):
        return "terabox"
    return None


async def _call_diskwala_resolver(resolver_url: str, share_url: str) -> dict:
    p = urlparse(resolver_url)
    if p.scheme != "https" or not p.hostname:
        raise ValueError("DiskWala resolver must be an HTTPS URL.")
    origin = f"{p.scheme}://{p.netloc}"
    is_fetch_video = "fetch-video" in p.path
    params = {"url": share_url, "attempt": "0"} if is_fetch_video else {"q": share_url}
    req_headers = {"User-Agent": UA, "Accept": "*/*", "Referer": f"{origin}/"}

    timeout = aiohttp.ClientTimeout(total=45, connect=15)
    async with aiohttp.ClientSession(timeout=timeout, headers=req_headers) as s:
        async with s.get(resolver_url, params=params) as r:
            try:
                data = await r.json(content_type=None)
            except Exception:
                data = None
            if r.status >= 400:
                if isinstance(data, dict):
                    err = data.get("error") or data.get("message") or f"HTTP {r.status}"
                    det = data.get("details")
                    det_msg = det.get("error") if isinstance(det, dict) else det
                    extra = f" [{det_msg}]" if det_msg else ""
                    raise ValueError(f"DiskWala resolver error ({r.status}): {err}{extra}")
                body = (await r.text())[:200]
                raise ValueError(f"DiskWala resolver HTTP {r.status}: {body}")

    payload = (data or {}).get("data") if isinstance(data, dict) else {}
    if not isinstance(payload, dict):
        payload = {}
    f = payload.get("file") if isinstance(payload.get("file"), dict) else {}

    direct = (
        f.get("downloadUrl")
        or f.get("url")
        or payload.get("downloadUrl")
        or payload.get("url")
        or (data.get("url") if isinstance(data, dict) else None)
        or (data.get("downloadUrl") if isinstance(data, dict) else None)
    )
    failed_flag = isinstance(data, dict) and (
        data.get("success") is False
        or (data.get("status") is not None and str(data.get("status")).lower() not in ("success", "ok", "true"))
    )
    if not direct or failed_flag:
        err_msg = (data.get("error") or data.get("message") or "") if isinstance(data, dict) else ""
        detail = f" ({err_msg})" if err_msg else ""
        raise ValueError(
            f"DiskWala resolver could not resolve this share{detail}. "
            "It may be private, deleted, unsupported, or the resolver may be unavailable."
        )

    direct_abs = urljoin(f"{origin}/", str(direct))
    direct_abs = validate_url(direct_abs, set())
    name = str(
        f.get("name")
        or payload.get("name")
        or (data.get("title") if isinstance(data, dict) else None)
        or "diskwala_video"
    ).strip()
    ext = re.sub(r"[^a-z0-9]", "", str(f.get("extension") or "mp4").lower()) or "mp4"
    if not any(name.lower().endswith(e) for e in VIDEO_EXTS):
        name += "." + ext
    return {
        "url": direct_abs,
        "name": name,
        "size": int(f.get("size") or payload.get("size") or 0),
        "headers": {"User-Agent": UA, "Accept": "*/*", "Referer": f"{origin}/"},
    }


async def resolve_diskwala(url: str) -> dict:
    resolvers = []
    if DISKWALA_RESOLVER_URL:
        resolvers.append(DISKWALA_RESOLVER_URL)
    if DEFAULT_DISKWALA_API not in resolvers:
        resolvers.append(DEFAULT_DISKWALA_API)

    last_err: Exception | None = None
    for idx, resolver_url in enumerate(resolvers):
        try:
            return await _call_diskwala_resolver(resolver_url, url)
        except Exception as exc:
            last_err = exc
            if idx + 1 < len(resolvers):
                continue
    raise last_err or ValueError("DiskWala resolver is not configured.")


def _surl(final_url: str) -> str | None:
    p = urlparse(final_url)
    q = dict(parse_qsl(p.query))
    if q.get("surl"):
        return q["surl"]
    m = re.search(r"/s/([A-Za-z0-9_-]+)", p.path)
    if m:
        v = m.group(1)
        return v[1:] if v.startswith("1") and len(v) > 8 else v
    return None


def _extract_jstoken(html: str) -> str | None:
    for pattern in (
        r'fn%28%22([^%"]+)%22%29',
        r'fn\(["\']([^"\']+)["\']\)',
        r'jsToken\s*[:=]\s*["\']([^"\']+)["\']',
    ):
        m = re.search(pattern, html)
        if m:
            return unquote(m.group(1))
    return None


def _extract_logid(html: str) -> str:
    m = re.search(r'dp-logid=([^&"\']+)', html) or re.search(r'["\']logid["\']\s*[:=]\s*["\']([^"\']+)["\']', html, re.I)
    return m.group(1) if m else ""


def _pick_terabox_video(rows: list) -> dict | None:
    for item in rows:
        fname = str(item.get("server_filename", "")).lower()
        if fname.endswith(VIDEO_EXTS) and item.get("dlink"):
            return item
    return None


async def resolve_terabox(url: str) -> dict:
    if not TERABOX_COOKIE:
        raise ValueError(
            "TeraBox needs your own authorized session cookie. "
            "Set TERABOX_COOKIE in environment variables / Config Vars; never send it in chat."
        )
    timeout = aiohttp.ClientTimeout(total=45, connect=15)
    headers = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*", "Cookie": TERABOX_COOKIE}

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as s:
        async with s.get(url, allow_redirects=True) as r:
            r.raise_for_status()
            final = str(r.url)
            html = await r.text()

        parsed_final = urlparse(final)
        final_host = (parsed_final.hostname or "www.terabox.com").lower()
        base_origin = f"https://{final_host}"

        surl = _surl(final) or _surl(url)
        if not surl:
            raise ValueError("TeraBox link has no recognized share ID.")

        js_token = _extract_jstoken(html)
        logid = _extract_logid(html)
        rows = []

        if js_token:
            params = {
                "app_id": "250528",
                "web": "1",
                "channel": "dubox",
                "clienttype": "0",
                "jsToken": js_token,
                "page": "1",
                "num": "100",
                "by": "name",
                "order": "asc",
                "site_referer": final,
                "shorturl": surl,
                "root": "1",
            }
            if logid:
                params["dp-logid"] = logid

            async with s.get(f"{base_origin}/share/list", params=params, headers={**headers, "Referer": final}) as r:
                r.raise_for_status()
                data = await r.json(content_type=None)
            if data.get("errno"):
                raise ValueError("TeraBox API error: " + str(data.get("errmsg") or data.get("errno")))
            rows = data.get("list") or []

            # Traverse one subfolder level if root share contains only a folder
            if not _pick_terabox_video(rows):
                dirs = [row for row in rows if str(row.get("isdir")) == "1" and row.get("path")]
                if dirs:
                    sub_params = {**params, "root": "0", "dir": dirs[0]["path"]}
                    async with s.get(f"{base_origin}/share/list", params=sub_params, headers={**headers, "Referer": final}) as r2:
                        if r2.status == 200:
                            sub_data = await r2.json(content_type=None)
                            if not sub_data.get("errno"):
                                rows = sub_data.get("list") or rows
        else:
            # Fallback to shorturlinfo endpoint when inline jsToken is absent
            info_params = {"shorturl": surl, "root": "1"}
            async with s.get(f"{base_origin}/api/shorturlinfo", params=info_params, headers={**headers, "Referer": final}) as r:
                r.raise_for_status()
                info_data = await r.json(content_type=None)
            if info_data.get("errno"):
                raise ValueError("TeraBox page tokens were not found. Your cookie may be expired or the page changed.")
            rows = info_data.get("list") or []

    f = _pick_terabox_video(rows)
    if not f:
        raise ValueError("No directly downloadable video was found in this share.")

    direct = validate_url(str(f["dlink"]), set())
    dl_headers = {"User-Agent": UA, "Accept": "*/*", "Referer": f"{base_origin}/"}
    dl_host = (urlparse(direct).hostname or "").lower()
    final_reg_domain = ".".join(final_host.split(".")[-2:])
    if (
        dl_host == final_host
        or dl_host.endswith("." + final_reg_domain)
        or dl_host == "terabox.com"
        or dl_host.endswith(".terabox.com")
    ):
        dl_headers["Cookie"] = TERABOX_COOKIE

    return {
        "url": direct,
        "name": str(f.get("server_filename") or "terabox_video.mp4"),
        "size": int(f.get("size") or 0),
        "headers": dl_headers,
    }


async def resolve_share(url: str) -> dict:
    p = provider_for(url)
    if p == "diskwala":
        return await resolve_diskwala(url)
    if p == "terabox":
        return await resolve_terabox(url)
    raise ValueError("Unsupported share-link provider.")
