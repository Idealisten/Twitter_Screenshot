from __future__ import annotations

import json
import math
import mimetypes
import os
import re
from functools import lru_cache
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

import requests
from bs4 import BeautifulSoup
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from PIL import Image, ImageDraw, ImageFont, ImageOps
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
REQUEST_HEADERS = {
    "User-Agent": "XShareCardMaker/1.0 (+https://localhost)",
    "Accept": "application/json,text/html,image/*;q=0.9,*/*;q=0.8",
}
CARD_WIDTH = 980
CARD_PADDING_X = 62
RENDER_HOST = os.environ.get("RENDER_HOST", "127.0.0.1")
CHROMIUM_PATH = os.environ.get("CHROMIUM_PATH", "/usr/bin/chromium")


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
        "replying_to": tweet.get("replying_to") or "",
        "replying_to_status": tweet.get("replying_to_status") or "",
    }
    if tweet.get("quote"):
        data["quote"] = parse_api_tweet(tweet["quote"], tweet["quote"].get("url") or raw_url)
    return data


def fetch_fxtwitter(raw_url: str, include_reply_parent: bool = True) -> dict[str, Any]:
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
    if include_reply_parent and data.get("replying_to") and data.get("replying_to_status"):
        parent_url = f"https://x.com/{quote(str(data['replying_to']))}/status/{quote(str(data['replying_to_status']))}"
        if data.get("id") != data.get("replying_to_status"):
            try:
                data["reply_parent"] = fetch_fxtwitter(parent_url, include_reply_parent=False)
            except Exception as exc:  # noqa: BLE001 - keep rendering the reply if the parent fetch fails.
                data.setdefault("warnings", []).append(f"原帖抓取失败：{exc}")
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
                data["warnings"] = [*(data.get("warnings") or []), *errors]
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
    handler.send_header("Cache-Control", "no-store, max-age=0")
    handler.send_header("Pragma", "no-cache")
    handler.send_header("Content-Length", str(len(content)))
    handler.end_headers()
    handler.wfile.write(content)


def image_response(handler: BaseHTTPRequestHandler, status: int, content: bytes, filename: str) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", "image/png")
    handler.send_header("Content-Disposition", f'attachment; filename="{filename}"')
    handler.send_header("Content-Length", str(len(content)))
    handler.end_headers()
    handler.wfile.write(content)


def text_response(handler: BaseHTTPRequestHandler, status: int, message: str) -> None:
    payload = message.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def browser_render_url(raw_url: str) -> str:
    return f"http://{RENDER_HOST}:{PORT}/static/render.html?url={quote(raw_url, safe='')}"


def render_tweet_png_in_browser(raw_url: str) -> bytes:
    launch_options: dict[str, Any] = {
        "headless": True,
        "args": ["--no-sandbox", "--disable-dev-shm-usage"],
    }
    chromium_path = Path(CHROMIUM_PATH)
    if chromium_path.exists():
        launch_options["executable_path"] = str(chromium_path)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**launch_options)
        try:
            page = browser.new_page(
                viewport={"width": CARD_WIDTH, "height": 2400},
                device_scale_factor=2,
            )
            page.goto(browser_render_url(raw_url), wait_until="networkidle", timeout=45000)
            page.wait_for_function("window.__xshotRenderStatus === 'ready' || window.__xshotRenderStatus === 'error'", timeout=45000)
            status = page.evaluate("window.__xshotRenderStatus")
            if status != "ready":
                error = page.evaluate("window.__xshotRenderError || '浏览器渲染失败。'")
                raise FetchError(error)
            data_url = page.locator("#cardCanvas").evaluate("canvas => canvas.toDataURL('image/png')")
            match = re.fullmatch(r"data:image/png;base64,(.+)", data_url)
            if not match:
                raise FetchError("浏览器没有返回有效 PNG。")
            import base64

            return base64.b64decode(match.group(1))
        except PlaywrightTimeoutError as exc:
            raise FetchError("浏览器渲染超时，请稍后重试。") from exc
        finally:
            browser.close()


def font_candidates(bold: bool = False) -> list[str]:
    if bold:
        return [
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
    return [
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]


@lru_cache(maxsize=64)
def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in font_candidates(bold):
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default(size=size)


def has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]", text))


def text_profile(text: str) -> dict[str, int]:
    if has_cjk(text):
        return {"size": 31, "line_height": 40}
    if re.search(r"[\u0600-\u06ff\u0590-\u05ff]", text):
        return {"size": 29, "line_height": 42}
    return {"size": 30, "line_height": 40}


def text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> float:
    return draw.textlength(text, font=font)


def tokenize_text(text: str) -> list[str]:
    cjk = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]")
    tokens: list[str] = []
    current = ""
    for char in text:
        if char == "\n":
            if current:
                tokens.append(current)
            current = ""
            tokens.append("\n")
        elif cjk.match(char):
            if current:
                tokens.append(current)
            current = ""
            tokens.append(char)
        elif char.isspace():
            current += char
            tokens.append(current)
            current = ""
        else:
            current += char
    if current:
        tokens.append(current)
    return tokens


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    tokens = tokenize_text(text)
    lines: list[str] = []
    line = ""
    for token in tokens:
        if token == "\n":
            lines.append(line.rstrip())
            line = ""
            continue

        candidate = line + token
        if text_width(draw, candidate, font) <= max_width:
            line = candidate
            continue

        if line:
            lines.append(line.rstrip())
            line = token.lstrip()
            continue

        fragment = ""
        for char in token:
            next_fragment = fragment + char
            if text_width(draw, next_fragment, font) > max_width and fragment:
                lines.append(fragment)
                fragment = char
            else:
                fragment = next_fragment
        line = fragment

    if line or not lines:
        lines.append(line.rstrip())
    return lines


def draw_text_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    x: int,
    y: int,
    font: ImageFont.ImageFont,
    fill: str,
    line_height: int,
) -> int:
    current_y = y
    for line in lines:
        draw.text((x, current_y), line, font=font, fill=fill)
        current_y += line_height
    return current_y


def fetch_image(url: str | None) -> Image.Image | None:
    if not url:
        return None
    try:
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=18)
        response.raise_for_status()
        image = Image.open(BytesIO(response.content))
        return ImageOps.exif_transpose(image).convert("RGB")
    except Exception:
        return None


def rounded_paste(base: Image.Image, image: Image.Image, box: tuple[int, int, int, int], radius: int) -> None:
    x, y, width, height = box
    image_ratio = image.width / max(1, image.height)
    box_ratio = width / max(1, height)
    if image_ratio > box_ratio:
        resize_height = height
        resize_width = round(height * image_ratio)
    else:
        resize_width = width
        resize_height = round(width / image_ratio)
    resized = image.resize((resize_width, resize_height), Image.Resampling.LANCZOS)
    left = max(0, (resize_width - width) // 2)
    top = max(0, (resize_height - height) // 2)
    cropped = resized.crop((left, top, left + width, top + height))
    mask = Image.new("L", (width, height), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle((0, 0, width, height), radius=radius, fill=255)
    base.paste(cropped, (x, y), mask)


def draw_avatar(base: Image.Image, draw: ImageDraw.ImageDraw, image: Image.Image | None, x: int, y: int, size: int, name: str) -> None:
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, size, size), fill=255)
    if image:
        image_ratio = image.width / max(1, image.height)
        if image_ratio > 1:
            resize_height = size
            resize_width = round(size * image_ratio)
        else:
            resize_width = size
            resize_height = round(size / image_ratio)
        resized = image.resize((resize_width, resize_height), Image.Resampling.LANCZOS)
        left = (resize_width - size) // 2
        top = (resize_height - size) // 2
        cropped = resized.crop((left, top, left + size, top + size))
        base.paste(cropped, (x, y), mask)
        return

    draw.ellipse((x, y, x + size, y + size), fill="#e7eef2")
    initials = "".join(list((name or "X").strip())[:2]).upper()
    font = load_font(round(size * 0.34), True)
    bbox = draw.textbbox((0, 0), initials, font=font)
    draw.text(
        (x + size / 2 - (bbox[2] - bbox[0]) / 2, y + size / 2 - (bbox[3] - bbox[1]) / 2 - 1),
        initials,
        font=font,
        fill="#15211c",
    )


def draw_verified(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, color: str = "#1d9bf0") -> None:
    points: list[tuple[float, float]] = []
    for i in range(16):
        angle = (math.pi * 2 * i) / 16 - math.pi / 2
        radius = size / 2 if i % 2 == 0 else size * 0.42
        points.append((x + math.cos(angle) * radius, y + math.sin(angle) * radius))
    draw.polygon(points, fill=color)
    width = max(2, round(size * 0.1))
    draw.line(
        [(x - size * 0.2, y), (x - size * 0.05, y + size * 0.16), (x + size * 0.24, y - size * 0.18)],
        fill="#ffffff",
        width=width,
        joint="curve",
    )


def draw_x_logo(draw: ImageDraw.ImageDraw, x: int, y: int, size: int = 66) -> None:
    font = load_font(size, True)
    text = "X"
    bbox = draw.textbbox((0, 0), text, font=font)
    draw.text((x - (bbox[2] - bbox[0]) / 2, y - (bbox[3] - bbox[1]) / 2 - 8), text, font=font, fill="#0f1b16")


def draw_stat_icon(draw: ImageDraw.ImageDraw, kind: str, x: int, y: int, color: str) -> None:
    if kind == "reply":
        draw.rounded_rectangle((x + 2, y + 4, x + 36, y + 30), radius=15, outline=color, width=4)
        draw.line((x + 14, y + 29, x + 8, y + 38, x + 22, y + 31), fill=color, width=4)
    elif kind == "retweet":
        draw.line((x + 8, y + 10, x + 30, y + 10, x + 30, y + 22), fill=color, width=4)
        draw.line((x + 24, y + 16, x + 30, y + 22, x + 36, y + 16), fill=color, width=4)
        draw.line((x + 32, y + 31, x + 10, y + 31, x + 10, y + 19), fill=color, width=4)
        draw.line((x + 16, y + 25, x + 10, y + 19, x + 4, y + 25), fill=color, width=4)
    else:
        draw.line(
            [
                (x + 20, y + 37),
                (x + 7, y + 25),
                (x + 5, y + 14),
                (x + 12, y + 7),
                (x + 20, y + 12),
                (x + 28, y + 7),
                (x + 35, y + 14),
                (x + 33, y + 25),
                (x + 20, y + 37),
            ],
            fill=color,
            width=4,
            joint="curve",
        )


def media_height(items: list[dict[str, Any]], images: list[Image.Image | None], width: int) -> int:
    if not items:
        return 0
    if len(items) == 1:
        image = images[0] if images else None
        if image:
            ratio = image.height / max(1, image.width)
            return min(780, max(360, round(width * ratio)))
        return 440
    return 560


def draw_video_overlay(draw: ImageDraw.ImageDraw, x: int, y: int, width: int, height: int, item: dict[str, Any]) -> None:
    center = (x + width // 2, y + height // 2)
    draw.ellipse((center[0] - 38, center[1] - 38, center[0] + 38, center[1] + 38), fill=(0, 0, 0, 120))
    draw.polygon(
        [(center[0] - 10, center[1] - 20), (center[0] - 10, center[1] + 20), (center[0] + 24, center[1])],
        fill="#ffffff",
    )
    duration = item.get("duration")
    if duration:
        label = str(duration)
        font = load_font(20, True)
        label_width = int(text_width(draw, label, font)) + 24
        draw.rounded_rectangle((x + 18, y + height - 48, x + 18 + label_width, y + height - 16), radius=6, fill="#000000")
        draw.text((x + 30, y + height - 43), label, font=font, fill="#ffffff")


def draw_media(
    base: Image.Image,
    draw: ImageDraw.ImageDraw,
    items: list[dict[str, Any]],
    images: list[Image.Image | None],
    x: int,
    y: int,
    width: int,
) -> int:
    height = media_height(items, images, width)
    if not items:
        return 0
    draw.rounded_rectangle((x, y, x + width, y + height), radius=18, fill="#f1f5f7", outline="#d1dee5", width=2)
    count = min(len(items), 4)
    gap = 4
    boxes: list[tuple[int, int, int, int]] = []
    if count == 1:
        boxes = [(x, y, width, height)]
    elif count == 2:
        cell_w = (width - gap) // 2
        boxes = [(x, y, cell_w, height), (x + cell_w + gap, y, width - cell_w - gap, height)]
    else:
        cell_w = (width - gap) // 2
        cell_h = (height - gap) // 2
        boxes = [
            (x, y, cell_w, cell_h),
            (x + cell_w + gap, y, width - cell_w - gap, cell_h),
            (x, y + cell_h + gap, cell_w, height - cell_h - gap),
            (x + cell_w + gap, y + cell_h + gap, width - cell_w - gap, height - cell_h - gap),
        ][:count]

    for index, box in enumerate(boxes):
        image = images[index] if index < len(images) else None
        item = items[index]
        if image:
            rounded_paste(base, image, box, 18 if count == 1 else 0)
        else:
            bx, by, bw, bh = box
            draw.rectangle((bx, by, bx + bw, by + bh), fill="#eef3f6")
        if item.get("type") != "photo" or item.get("badge"):
            draw_video_overlay(draw, box[0], box[1], box[2], box[3], item)
    draw.rounded_rectangle((x, y, x + width, y + height), radius=18, outline="#d1dee5", width=2)
    return height


def verified_color(author: dict[str, Any]) -> str:
    return "#f4c430" if author.get("verification_type") in {"Business", "Government"} else "#1d9bf0"


def draw_quote_card(
    base: Image.Image,
    draw: ImageDraw.ImageDraw,
    quote_tweet: dict[str, Any],
    x: int,
    y: int,
    width: int,
) -> int:
    author = quote_tweet.get("author") or {}
    profile = text_profile(quote_tweet.get("text") or "")
    text_font = load_font(max(24, profile["size"] - 2), False)
    text_lines = wrap_text(draw, quote_tweet.get("text") or "", text_font, width - 48)
    images = [fetch_image(item.get("url")) for item in quote_tweet.get("images", [])[:4]]
    media_items = quote_tweet.get("images", [])[:4]
    quote_media_height = media_height(media_items, images, width) if media_items else 0
    text_height = len(text_lines) * profile["line_height"]
    header_height = 70
    card_height = 26 + header_height + text_height + (20 if media_items else 0) + quote_media_height + 18

    draw.rounded_rectangle((x, y, x + width, y + card_height), radius=20, fill="#ffffff", outline="#d1dee5", width=2)
    avatar = fetch_image(author.get("avatar"))
    draw_avatar(base, draw, avatar, x + 26, y + 26, 48, author.get("name") or "X")
    name_font = load_font(30, True)
    meta_font = load_font(29, False)
    name = author.get("name") or "X User"
    name_x = x + 86
    name_y = y + 31
    draw.text((name_x, name_y), name, font=name_font, fill="#0f1b16")
    name_w = text_width(draw, name, name_font)
    meta_x = name_x + int(name_w) + 12
    if author.get("verified"):
        draw_verified(draw, meta_x + 16, name_y + 17, 30, verified_color(author))
        meta_x += 42
    meta = f"@{author.get('handle') or 'user'}"
    if quote_tweet.get("date_label"):
        meta += f" · {quote_tweet['date_label']}"
    draw.text((meta_x, name_y + 1), meta, font=meta_font, fill="#536372")

    body_y = y + 96
    body_y = draw_text_lines(draw, text_lines, x + 26, body_y, text_font, "#111b16", profile["line_height"])
    if media_items:
        body_y += 20
        draw_media(base, draw, media_items, images, x, body_y, width)
    return card_height


def measure_quote_card(draw: ImageDraw.ImageDraw, quote_tweet: dict[str, Any], width: int) -> int:
    profile = text_profile(quote_tweet.get("text") or "")
    text_font = load_font(max(24, profile["size"] - 2), False)
    text_lines = wrap_text(draw, quote_tweet.get("text") or "", text_font, width - 48)
    media_items = quote_tweet.get("images", [])[:4]
    quote_media_height = media_height(media_items, [], width) if media_items else 0
    text_height = len(text_lines) * profile["line_height"]
    return 26 + 70 + text_height + (20 if media_items else 0) + quote_media_height + 18


def visible_stats(stats: dict[str, Any] | None) -> list[tuple[str, str]]:
    stats = stats or {}
    values = [("reply", stats.get("replies")), ("retweet", stats.get("retweets")), ("like", stats.get("likes"))]
    return [(kind, str(value)) for kind, value in values if value not in {None, ""}]


def render_tweet_png(tweet: dict[str, Any]) -> bytes:
    padding_x = CARD_PADDING_X
    max_width = CARD_WIDTH - padding_x * 2
    measure_img = Image.new("RGB", (CARD_WIDTH, 200), "white")
    measure_draw = ImageDraw.Draw(measure_img)

    profile = text_profile(tweet.get("text") or "")
    text_font = load_font(profile["size"], False)
    text_lines = wrap_text(measure_draw, tweet.get("text") or "", text_font, max_width)
    text_height = len(text_lines) * profile["line_height"]
    media_items = tweet.get("images", [])[:4]
    media_images = [fetch_image(item.get("url")) for item in media_items]
    main_media_height = media_height(media_items, media_images, max_width)
    quote_height = 0
    if tweet.get("quote"):
        quote_height = measure_quote_card(measure_draw, tweet["quote"], max_width)

    content_top = 192
    footer_height = 74
    card_height = content_top + text_height
    if media_items:
        card_height += 28 + main_media_height
    if tweet.get("quote"):
        card_height += 28 + quote_height
    card_height += footer_height + 40

    image = Image.new("RGB", (CARD_WIDTH, card_height), "white")
    draw = ImageDraw.Draw(image)
    author = tweet.get("author") or {}
    avatar = fetch_image(author.get("avatar"))
    draw_avatar(image, draw, avatar, padding_x, 75, 68, author.get("name") or "X")

    name_font = load_font(29, True)
    handle_font = load_font(30, False)
    name_y = 80
    fitted_name = author.get("name") or "X User"
    max_name_width = CARD_WIDTH - padding_x * 2 - 68 - 130
    while text_width(draw, fitted_name, name_font) > max_name_width and len(fitted_name) > 3:
        fitted_name = f"{fitted_name[:-2]}…"
    draw.text((padding_x + 86, name_y), fitted_name, font=name_font, fill="#0f1b16")
    name_w = text_width(draw, fitted_name, name_font)
    if author.get("verified"):
        draw_verified(draw, padding_x + 86 + int(name_w) + 24, 93, 31, verified_color(author))
    draw.text((padding_x + 86, 122), f"@{author.get('handle') or 'user'}", font=handle_font, fill="#536372")
    draw_x_logo(draw, CARD_WIDTH - 94, 116)

    y = content_top
    y = draw_text_lines(draw, text_lines, padding_x, y, text_font, "#111b16", profile["line_height"])
    if media_items:
        y += 28
        y += draw_media(image, draw, media_items, media_images, padding_x, y, max_width)
    if tweet.get("quote"):
        y += 28
        y += draw_quote_card(image, draw, tweet["quote"], padding_x, y, max_width)

    footer_y = card_height - 65
    stat_color = "#536372"
    stat_font = load_font(29, False)
    stat_x = padding_x
    for kind, value in visible_stats(tweet.get("stats")):
        draw_stat_icon(draw, kind, stat_x, footer_y - 20, stat_color)
        draw.text((stat_x + 50, footer_y - 17), value, font=stat_font, fill=stat_color)
        stat_x += 50 + int(text_width(draw, value, stat_font)) + 32

    date_text = tweet.get("date_label") or ""
    views = (tweet.get("stats") or {}).get("views")
    if date_text or views:
        right_x = CARD_WIDTH - padding_x
        date_font = load_font(28, False)
        views_font = load_font(28, True)
        if views:
            views_text = f"{views} Views"
            views_w = text_width(draw, views_text, views_font)
            draw.text((right_x - views_w, footer_y - 17), views_text, font=views_font, fill="#0f1b16")
            date_label = f"{date_text} · "
            date_w = text_width(draw, date_label, date_font)
            draw.text((right_x - views_w - date_w, footer_y - 17), date_label, font=date_font, fill=stat_color)
        else:
            date_w = text_width(draw, date_text, date_font)
            draw.text((right_x - date_w, footer_y - 17), date_text, font=date_font, fill=stat_color)

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


class AppHandler(BaseHTTPRequestHandler):
    server_version = "XShareCard/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            serve_file(self, STATIC / "index.html")
            return
        if parsed.path in {"/favicon.ico", "/favicon.svg"}:
            serve_file(self, STATIC / "favicon.svg")
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
        if parsed.path == "/api/render":
            self.render_image(parsed.query)
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        parsed_path = urlparse(self.path).path
        if parsed_path not in {"/api/tweet", "/api/render"}:
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length") or "0")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            url = payload.get("url", "")
            if not isinstance(url, str) or not url.strip():
                raise FetchError("请先输入帖子链接。")
            if parsed_path == "/api/render":
                info = parse_status_url(url)
                png = render_tweet_png_in_browser(url)
                image_response(self, 200, png, f"x-share-card-{info['status_id']}.png")
            else:
                data = fetch_tweet(url)
                json_response(self, 200, {"ok": True, "tweet": data})
        except FetchError as exc:
            if parsed_path == "/api/render":
                text_response(self, 422, str(exc))
            else:
                json_response(self, 422, {"ok": False, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            if parsed_path == "/api/render":
                text_response(self, 500, f"服务器处理失败：{exc}")
            else:
                json_response(self, 500, {"ok": False, "error": f"服务器处理失败：{exc}"})

    def render_image(self, query: str) -> None:
        url = unquote((parse_qs(query).get("url") or [""])[0])
        try:
            if not url.strip():
                raise FetchError("请先提供帖子链接。")
            info = parse_status_url(url)
            png = render_tweet_png_in_browser(url)
            image_response(self, 200, png, f"x-share-card-{info['status_id']}.png")
        except FetchError as exc:
            text_response(self, 422, str(exc))
        except Exception as exc:  # noqa: BLE001
            text_response(self, 500, f"服务器处理失败：{exc}")

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
