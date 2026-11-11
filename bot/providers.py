import re
from urllib.parse import urlparse, parse_qsl
import aiohttp
from .config import DISKWALA_RESOLVER_URL, TERABOX_COOKIE
from .downloader import validate_url

VIDEO_EXTS = (".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0 Safari/537.36"

def provider_for(url):
    host=(urlparse(url).hostname or "").lower()
    if host == "diskwala.com" or host.endswith(".diskwala.com"): return "diskwala"
    if any(x in host for x in ("terabox","1024tera","nephobox","freeterabox","mirrobox","dubox","4funbox","momerybox","tibibox")): return "terabox"
    return None

async def resolve_diskwala(url):
    if not DISKWALA_RESOLVER_URL: raise ValueError("DISKWALA_RESOLVER_URL is not configured.")
    p=urlparse(DISKWALA_RESOLVER_URL)
    if p.scheme != "https" or not p.hostname: raise ValueError("DiskWala resolver must be an HTTPS URL.")
    timeout=aiohttp.ClientTimeout(total=45,connect=15)
    async with aiohttp.ClientSession(timeout=timeout,headers={"User-Agent":UA}) as s:
        async with s.get(DISKWALA_RESOLVER_URL,params={"q":url}) as r:
            r.raise_for_status()
            data=await r.json(content_type=None)
    f=((data or {}).get("data") or {}).get("file") or {}
    direct=f.get("downloadUrl")
    if not (data or {}).get("success") or not direct:
        raise ValueError("DiskWala resolver could not resolve this share. It may be private, deleted, unsupported, or the resolver may be unavailable.")
    direct=validate_url(str(direct),set())
    name=str(f.get("name") or "diskwala_video").strip()
    ext=re.sub(r"[^a-z0-9]","",str(f.get("extension") or "mp4").lower()) or "mp4"
    if not name.lower().endswith("."+ext): name += "."+ext
    return {"url":direct,"name":name,"size":int(f.get("size") or 0),"headers":{"User-Agent":UA,"Accept":"*/*"}}

def _surl(final_url):
    p=urlparse(final_url)
    q=dict(parse_qsl(p.query))
    if q.get("surl"): return q["surl"]
    m=re.search(r"/s/([A-Za-z0-9_-]+)",p.path)
    if m:
        v=m.group(1)
        return v[1:] if v.startswith("1") else v
    return None

async def resolve_terabox(url):
    if not TERABOX_COOKIE:
        raise ValueError("TeraBox needs your own authorized session cookie. Set TERABOX_COOKIE as a Koyeb Secret; never send it in chat.")
    timeout=aiohttp.ClientTimeout(total=45,connect=15)
    headers={"User-Agent":UA,"Accept":"text/html,application/xhtml+xml,*/*","Cookie":TERABOX_COOKIE}
    async with aiohttp.ClientSession(timeout=timeout,headers=headers) as s:
        async with s.get(url,allow_redirects=True) as r:
            r.raise_for_status()
            final=str(r.url)
        async with s.get(final,allow_redirects=True) as r:
            r.raise_for_status()
            html=await r.text()
        surl=_surl(final)
        if not surl: raise ValueError("TeraBox link has no recognized share ID.")
        tm=re.search(r'jsToken\s*[:=]\s*["\']([^"\']+)',html) or re.search(r'fn%28%22([^%]+)%22%29',html)
        lm=re.search(r'dp-logid=([^&"\']+)',html)
        if not tm or not lm: raise ValueError("TeraBox page tokens were not found. Your cookie may be expired or the page changed.")
        params={"app_id":"250528","web":"1","channel":"dubox","clienttype":"0","jsToken":tm.group(1),"dp-logid":lm.group(1),"page":"1","num":"100","by":"name","order":"asc","site_referer":final,"shorturl":surl,"root":"1,"}
        async with s.get("https://www.terabox.com/share/list",params=params,headers={**headers,"Referer":final}) as r:
            r.raise_for_status()
            data=await r.json(content_type=None)
    if data.get("errno"): raise ValueError("TeraBox API error: "+str(data.get("errmsg") or data.get("errno")))
    rows=data.get("list") or []
    files=[f for f in rows if str(f.get("server_filename","")).lower().endswith(VIDEO_EXTS) and f.get("dlink")]
    if not files: raise ValueError("No directly downloadable video was found in this share.")
    f=files[0]
    direct=validate_url(str(f["dlink"]),set())
    dl_headers={"User-Agent":UA,"Accept":"*/*","Referer":"https://www.terabox.com/"}\n    dl_host=(urlparse(direct).hostname or "").lower()\n    if dl_host == "terabox.com" or dl_host.endswith(".terabox.com"):\n        dl_headers["Cookie"]=TERABOX_COOKIE\n    return {"url":direct,"name":str(f.get("server_filename") or "terabox_video.mp4"),"size":int(f.get("size") or 0),"headers":dl_headers}

async def resolve_share(url):
    p=provider_for(url)
    if p=="diskwala": return await resolve_diskwala(url)
    if p=="terabox": return await resolve_terabox(url)
    raise ValueError("Unsupported share-link provider.")
