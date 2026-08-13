import html2text
import httpx

MAX = 50_000


def web_fetch(url: str) -> str:
    try:
        resp = httpx.get(url, timeout=20.0, headers={"User-Agent": "exp1-hermes/0.1"}, follow_redirects=True)
    except httpx.HTTPError as e:
        return f"ERROR: {e}"
    body = resp.text or ""
    ctype = (resp.headers.get("content-type") or "").lower()
    if "html" in ctype:
        body = html2text.html2text(body)
    if len(body) > MAX:
        body = body[:MAX] + "\n...[truncated]"
    if resp.status_code != 200:
        return f"ERROR: HTTP {resp.status_code}\n{body}"
    return body
