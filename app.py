from __future__ import annotations

import json
import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

import requests
from bs4 import BeautifulSoup
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
HOST = "127.0.0.1"
PORT = 8000
REQUEST_HEADERS = {
    "User-Agent": "XShareCardMaker/1.0 (+https://localhost)",
    "Accept": "application/json,text/html,image/*;q=0.9,*/*;q=0.8",
}


class FetchError(Exception):
    pass


def parse_status_url(raw_url: str) -> dict[str, str]:
    parsed = urlparse(raw_url.strip())
    host = parsed.netloc.lower().removeprefix("www.")
    if host not in {"x.com", "twitter.com", "mobile.twitter.com", "fixupx.com", "fxtwitter.com", "vxtwitter.com"}:
        raise FetchError("请输入 x.com 或 twitter.com 的帖子链接。")

    parts = [part for part in parsed.path.split("/") if part]
    try:
        status_index = parts.index("status")
    except ValueError:
        try:
            status_index = parts.index("statuses")
        except ValueError as exc:
            raise FetchError("链接里没有找到 status ID，请确认是单条帖子链接。") from exc

    if status_index == 0 or status_index + 1 >= len(parts):
        raise FetchError("链接格式不完整，请粘贴完整的帖子链接。")

    screen_name = parts[status_index - 1]
    status_id = re.sub(r"\D.*$", "", parts[status_index + 1])
    if not re.fullmatch(r"\d{8,25}", status_id):
        raise FetchError("帖子 ID 看起来不正确。")

    return {"screen_name": screen_name, "status_id": status_id}


def compact_count(value: Any) -> str:
    if value is None:
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)

    if number >= 1_000_000:
        text = f"{number / 1_000_000:.1f}M"
    elif number >= 1_000:
        text = f"{number / 1_000:.1f}K"
    else:
        text = str(int(number))
    return text.replace(".0", "")


def parse_created_at(value: str | None) -> dict[str, str]:
    if not value:
        return {"iso": "", "label": ""}
    formats = [
        "%a %b %d %H:%M:%S %z %Y",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return {
                "iso": dt.isoformat(),
                "label": dt.strftime("%b %-d, %Y"),
            }
        except ValueError:
            continue
    return {"iso": value, "label": value}


def clean_text(text: str) -> str:
    text = re.sub(r"https://t\.co/\S+", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_media(tweet: dict[str, Any]) -> list[dict[str, Any]]:
    media = tweet.get("media") or {}
    images: list[dict[str, Any]] = []

    media_items = media.get("photos") or media.get("all") or []
    seen_urls: set[str] = set()
    for photo in media_items:
        if photo.get("type") != "photo":
            continue
        if photo.get("url") and photo["url"] not in seen_urls:
            seen_urls.add(photo["url"])
            images.append(
                {
                    "type": "photo",
                    "url": photo["url"],
                    "width": photo.get("width"),
                    "height": photo.get("height"),
                    "alt": photo.get("altText") or "",
                }
            )

    for photo in media.get("photos") or []:
        if photo.get("url") and photo["url"] not in seen_urls:
            seen_urls.add(photo["url"])
            images.append(
                {
                    "type": "photo",
                    "url": photo["url"],
                    "width": photo.get("width"),
                    "height": photo.get("height"),
                    "alt": photo.get("altText") or "",
                }
            )

    mosaic = media.get("mosaic")
    if mosaic and mosaic.get("formats"):
        mosaic_url = mosaic["formats"].get("jpeg") or mosaic["formats"].get("webp")
        if mosaic_url and not images:
            images.append(
                {
                    "type": "photo",
                    "url": mosaic_url,
                    "width": mosaic.get("width"),
                    "height": mosaic.get("height"),
                    "alt": "",
                }
            )

    for video in media.get("videos") or []:
        thumb = video.get("thumbnail_url")
        if thumb and thumb not in seen_urls:
            seen_urls.add(thumb)
            images.append(
                {
                    "type": video.get("type") or "video",
                    "url": thumb,
                    "width": video.get("width"),
                    "height": video.get("height"),
                    "alt": "video thumbnail",
                    "badge": "VIDEO",
                    "duration": video.get("duration"),
                }
            )

    return images


def parse_api_tweet(tweet: dict[str, Any], raw_url: str) -> dict[str, Any]:
    author = tweet.get("author") or {}
    article = tweet.get("article") or {}
    images = extract_media(tweet)

    cover = article.get("cover_media") or {}
    cover_info = cover.get("media_info") or {}
    cover_url = cover_info.get("original_img_url")
    if cover_url and not images:
        images.append(
            {
                "type": "photo",
                "url": cover_url,
                "width": cover_info.get("original_img_width"),
                "height": cover_info.get("original_img_height"),
                "alt": article.get("title") or "",
            }
        )

    text = clean_text(tweet.get("text") or "")
    if not text and isinstance(tweet.get("raw_text"), dict):
        text = clean_text(tweet["raw_text"].get("text") or "")
    if not text and article:
        text = clean_text("\n\n".join(part for part in [article.get("title"), article.get("preview_text")] if part))

    verification = author.get("verification")
    verified = bool(author.get("verified") or author.get("is_blue_verified"))
    verification_type = ""
    if isinstance(verification, dict):
        verified = verified or bool(verification.get("verified"))
        verification_type = verification.get("type") or ""

    created = parse_created_at(tweet.get("created_at"))
    data = {
        "url": tweet.get("url") or raw_url,
        "id": tweet.get("id") or "",
        "text": text,
        "author": {
            "name": author.get("name") or author.get("screen_name") or "X User",
            "handle": author.get("screen_name") or "user",
            "avatar": author.get("avatar_url") or "",
            "verified": verified,
            "verification_type": verification_type,
        },
        "created_at": created["iso"],
        "date_label": created["label"],
        "stats": {
            "replies": compact_count(tweet.get("replies")),
            "retweets": compact_count(tweet.get("retweets")),
            "likes": compact_count(tweet.get("likes")),
            "views": compact_count(tweet.get("views")),
        },
        "images": images[:4],
        "lang": tweet.get("lang") or "",
    }
    if tweet.get("quote"):
        data["quote"] = parse_api_tweet(tweet["quote"], tweet["quote"].get("url") or raw_url)
    return data


def fetch_fxtwitter(raw_url: str) -> dict[str, Any]:
    info = parse_status_url(raw_url)
    api_url = f"https://api.fxtwitter.com/{quote(info['screen_name'])}/status/{info['status_id']}"
    response = requests.get(api_url, headers=REQUEST_HEADERS, timeout=12)
    if response.status_code >= 400:
        raise FetchError(f"FixTweet API 返回 {response.status_code}。")
    payload = response.json()
    if payload.get("code") != 200 or not payload.get("tweet"):
        raise FetchError(payload.get("message") or "FixTweet API 没有返回帖子。")

    data = parse_api_tweet(payload["tweet"], raw_url)
    data["source"] = "fxtwitter"
    if not data["id"]:
        data["id"] = info["status_id"]
    return data


def fetch_oembed(raw_url: str) -> dict[str, Any]:
    info = parse_status_url(raw_url)
    endpoint = "https://publish.twitter.com/oembed"
    response = requests.get(
        endpoint,
        params={"url": raw_url, "omit_script": "true", "dnt": "true"},
        headers=REQUEST_HEADERS,
        timeout=12,
    )
    if response.status_code >= 400:
        raise FetchError(f"X oEmbed 返回 {response.status_code}。")
    payload = response.json()
    soup = BeautifulSoup(payload.get("html", ""), "html.parser")
    paragraph = soup.find("p")
    text = paragraph.get_text("\n", strip=True) if paragraph else ""
    author_url = payload.get("author_url") or ""
    handle = info["screen_name"]
    if author_url:
        path_parts = [part for part in urlparse(author_url).path.split("/") if part]
        if path_parts:
            handle = path_parts[0]

    link = soup.find("a", href=re.compile(r"/status/"))
    date_label = link.get_text(strip=True) if link else ""
    return {
        "source": "oembed",
        "url": raw_url,
        "id": info["status_id"],
        "text": clean_text(text),
        "author": {
            "name": payload.get("author_name") or handle,
            "handle": handle,
            "avatar": "",
            "verified": False,
            "verification_type": "",
        },
        "created_at": "",
        "date_label": date_label,
        "stats": {"replies": "", "retweets": "", "likes": "", "views": ""},
        "images": [],
        "lang": "",
    }


def fetch_tweet(raw_url: str) -> dict[str, Any]:
    parse_status_url(raw_url)
    errors: list[str] = []
    for fetcher in (fetch_fxtwitter, fetch_oembed):
        try:
            data = fetcher(raw_url)
            if data.get("text") or data.get("images"):
                data["warnings"] = errors
                return data
        except Exception as exc:  # noqa: BLE001 - surface provider fallbacks to the UI.
            errors.append(str(exc))
    raise FetchError("无法抓取这条帖子。可能是私密、已删除、受地区限制，或临时被 X 拦截。")


def json_response(handler: BaseHTTPRequestHandler, status: int, body: dict[str, Any]) -> None:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def serve_file(handler: BaseHTTPRequestHandler, path: Path) -> None:
    if not path.exists() or not path.is_file():
        handler.send_error(404)
        return
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    content = path.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", mime_type)
    handler.send_header("Content-Length", str(len(content)))
    handler.end_headers()
    handler.wfile.write(content)


class AppHandler(BaseHTTPRequestHandler):
    server_version = "XShareCard/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            serve_file(self, STATIC / "index.html")
            return
        if parsed.path.startswith("/static/"):
            requested = (STATIC / parsed.path.removeprefix("/static/")).resolve()
            if STATIC.resolve() not in requested.parents and requested != STATIC.resolve():
                self.send_error(403)
                return
            serve_file(self, requested)
            return
        if parsed.path == "/api/proxy-image":
            self.proxy_image(parsed.query)
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/tweet":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length") or "0")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            url = payload.get("url", "")
            if not isinstance(url, str) or not url.strip():
                raise FetchError("请先输入帖子链接。")
            data = fetch_tweet(url)
            json_response(self, 200, {"ok": True, "tweet": data})
        except FetchError as exc:
            json_response(self, 422, {"ok": False, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            json_response(self, 500, {"ok": False, "error": f"服务器处理失败：{exc}"})

    def proxy_image(self, query: str) -> None:
        url = unquote((parse_qs(query).get("url") or [""])[0])
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            self.send_error(400)
            return
        try:
            response = requests.get(url, headers=REQUEST_HEADERS, timeout=18)
            response.raise_for_status()
        except requests.RequestException:
            self.send_error(502)
            return

        content_type = response.headers.get("Content-Type", "image/jpeg").split(";")[0]
        if not content_type.startswith("image/"):
            self.send_error(415)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("Content-Length", str(len(response.content)))
        self.end_headers()
        self.wfile.write(response.content)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), AppHandler)
    print(f"X share card maker running at http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
