"""Draft ReFormat local server.

The server deliberately uses only the Python standard library so the project can
run on a fresh Python installation.  The browser does the visual editing; this
process only brokers Qwen Vision calls and imports basic web page metadata.
"""

from __future__ import annotations

import base64
import json
import os
import re
import threading
import urllib.error
import urllib.request
from io import BytesIO
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # Pillow is optional for the offline demo, required for grid hints.
    Image = ImageDraw = ImageFont = None


ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
HOST = os.environ.get("DRAFT_HOST", "127.0.0.1")
PORT = int(os.environ.get("DRAFT_PORT", "8765"))
QWEN_MODEL = os.environ.get("QWEN_MODEL", "qwen-3.6-plus")
QWEN_ENDPOINT = os.environ.get(
    "QWEN_ENDPOINT", "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
)


def load_dotenv() -> None:
    """Load a local .env without overwriting an explicitly exported variable."""

    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_dotenv()


def json_response(handler: BaseHTTPRequestHandler, payload: Any, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length)
    return json.loads(raw.decode("utf-8")) if raw else {}


def clean_json_text(text: str) -> str:
    """Extract the first JSON object/array from a model response."""

    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S).strip()
    first = min([p for p in (text.find("{"), text.find("[")) if p >= 0] or [0])
    last = max(text.rfind("}"), text.rfind("]"))
    return text[first : last + 1] if last >= first else text


def heuristic_regions() -> list[dict[str, Any]]:
    """A useful offline fallback for demos, tests, and missing API credentials."""

    return [
        {
            "id": "region-1",
            "label": "标题 / 题干",
            "kind": "text",
            "x": 7,
            "y": 6,
            "w": 86,
            "h": 14,
            "confidence": 0.82,
            "group": "A",
            "description": "检测到的主标题或题干区域",
        },
        {
            "id": "region-2",
            "label": "正文说明",
            "kind": "text",
            "x": 8,
            "y": 23,
            "w": 84,
            "h": 25,
            "confidence": 0.76,
            "group": "A",
            "description": "连贯文字段落，建议作为一个语义块",
        },
        {
            "id": "region-3",
            "label": "图表 / 图片",
            "kind": "image",
            "x": 10,
            "y": 53,
            "w": 38,
            "h": 30,
            "confidence": 0.71,
            "group": "B",
            "description": "图像、插图或数据图表",
        },
        {
            "id": "region-4",
            "label": "公式 / 结构式",
            "kind": "chemistry",
            "x": 53,
            "y": 55,
            "w": 37,
            "h": 24,
            "confidence": 0.68,
            "group": "B",
            "description": "化学结构式、数学公式或生物标注图",
        },
    ]


def add_coordinate_grid(image_data_url: str) -> str:
    """Overlay a light 10% coordinate grid while keeping the same aspect ratio.

    The grid is only sent to the vision model.  The browser keeps the original
    image, so grid lines and labels never appear in the final crop.
    """

    if Image is None or os.environ.get("QWEN_GRID", "1").lower() in {"0", "false", "off"}:
        return image_data_url
    try:
        header, encoded = image_data_url.split(",", 1)
        raw = base64.b64decode(encoded)
        source = Image.open(BytesIO(raw)).convert("RGB")
        # Keep payloads manageable while preserving percentage coordinates.
        source.thumbnail((2600, 2600), Image.Resampling.LANCZOS)
        base = source.convert("RGBA")
        overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        font = ImageFont.load_default()
        width, height = base.size
        for index in range(0, 11):
            x = round(width * index / 10)
            y = round(height * index / 10)
            major = index in {0, 5, 10}
            line_color = (42, 114, 181, 170 if major else 105)
            draw.line((x, 0, x, height), fill=line_color, width=2 if major else 1)
            draw.line((0, y, width, y), fill=line_color, width=2 if major else 1)
            label = str(index * 10)
            if index < 10:
                draw.rectangle((x + 2, 2, x + 22, 13), fill=(255, 255, 255, 205))
                draw.text((x + 4, 3), label, font=font, fill=(23, 78, 128, 255))
                draw.rectangle((2, max(2, y - 7), 24, y + 5), fill=(255, 255, 255, 205))
                draw.text((4, max(2, y - 6)), label, font=font, fill=(23, 78, 128, 255))
        result = Image.alpha_composite(base, overlay).convert("RGB")
        output = BytesIO()
        result.save(output, format="JPEG", quality=92, optimize=True)
        return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")
    except Exception as exc:
        print(f"Grid overlay skipped: {exc}")
        return image_data_url


def call_qwen(image_data_url: str, hint: str = "") -> tuple[list[dict[str, Any]], str]:
    api_key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("QWEN_API_KEY")
    if not api_key:
        return heuristic_regions(), "offline"

    model_image = add_coordinate_grid(image_data_url)
    prompt = f"""你是文档版面分析与语义分割专家。请分析这张草稿截图，给出适合后续编辑和分页的语义区域。
要求：
1. 这是“裁剪区域”识别，不是给整页画几个大框。每个题号、段落、图表、结构式、公式都要成为独立且紧致的内容块，尽量贴合可见内容，排除周围空白；相邻内容只有在语义上不可分时才合并。
2. 区域可以是不规则语义块，但输出用覆盖该内容的最小矩形表示；不要为了凑正方形而切断公式、化学结构式、图注或生物图片，也不要让一个框横跨多个无关对象。
3. 文字段落、题目、插图、表格、化学结构式、数学公式、生物图片分别识别。
3. 同属一个题目/图片编号集合的区域使用相同 group（例如 1、1a、1b 都用 group=\"1\"）。
4. 坐标为相对于原图的百分比 0-100，x/y 是左上角，w/h 是宽高；只输出 JSON，不要 Markdown。
5. label 使用简短中文，kind 只能是 text/image/table/chemistry/biology/formula/other。
6. 过滤页眉、页脚、装饰线和大面积空白；对每个真实内容给出边界，至少保留一个主内容区域。
7. 图片上叠加了蓝色 10% 坐标网格和刻度，左上角为 (0,0)，右下角为 (100,100)。网格、刻度数字不是内容，必须忽略它们；输出坐标仍对应没有网格的原始图片。
用户补充：{hint or '无'}
输出格式：{{\"regions\":[{{\"id\":\"r1\",\"label\":\"...\",\"kind\":\"text\",\"x\":0,\"y\":0,\"w\":20,\"h\":10,\"confidence\":0.92,\"group\":\"1\",\"description\":\"...\"}}]}}"""
    payload = {
        "model": QWEN_MODEL,
        "temperature": 0.1,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": model_image}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }
    request = urllib.request.Request(
        QWEN_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=80) as response:
            body = json.loads(response.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        parsed = json.loads(clean_json_text(str(content)))
        regions = parsed.get("regions", parsed if isinstance(parsed, list) else [])
        if not isinstance(regions, list) or not regions:
            raise ValueError("Qwen response contained no regions")
        return normalize_regions(regions), "qwen"
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"Qwen request failed, using offline layout: {exc}")
        return heuristic_regions(), "offline"


def normalize_regions(regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kinds = {"text", "image", "table", "chemistry", "biology", "formula", "other"}
    normalized: list[dict[str, Any]] = []
    for index, region in enumerate(regions[:40]):
        try:
            bbox = region.get("bbox") if isinstance(region.get("bbox"), list) else None
            raw_x = bbox[0] if bbox and len(bbox) >= 4 else region.get("x", 0)
            raw_y = bbox[1] if bbox and len(bbox) >= 4 else region.get("y", 0)
            raw_w = (bbox[2] - bbox[0]) if bbox and len(bbox) >= 4 else region.get("w", 10)
            raw_h = (bbox[3] - bbox[1]) if bbox and len(bbox) >= 4 else region.get("h", 10)
            scale = 0.1 if max(abs(float(raw_x or 0)), abs(float(raw_y or 0)), abs(float(raw_w or 0)), abs(float(raw_h or 0))) > 100 else 1
            x = max(0, min(100, float(raw_x) * scale))
            y = max(0, min(100, float(raw_y) * scale))
            w = max(1, min(100 - x, float(raw_w) * scale))
            h = max(1, min(100 - y, float(raw_h) * scale))
            item = {
                "id": str(region.get("id") or f"region-{index + 1}"),
                "label": str(region.get("label") or "语义区域")[:40],
                "kind": str(region.get("kind") or "other") if str(region.get("kind") or "other") in kinds else "other",
                "x": round(x, 2),
                "y": round(y, 2),
                "w": round(w, 2),
                "h": round(h, 2),
                "confidence": round(max(0, min(1, float(region.get("confidence", 0.6)))), 2),
                "group": str(region.get("group") or str(index + 1)),
                "description": str(region.get("description") or "语义内容区域")[:120],
            }
            normalized.append(item)
        except (TypeError, ValueError):
            continue
    return normalized or heuristic_regions()


def import_url(url: str) -> dict[str, Any]:
    if not re.match(r"^https?://", url, flags=re.I):
        raise ValueError("仅支持 http:// 或 https:// 网页地址")
    request = urllib.request.Request(url, headers={"User-Agent": "DraftReFormat/1.0"})
    with urllib.request.urlopen(request, timeout=15) as response:
        html = response.read(2_000_000).decode("utf-8", errors="ignore")
        final_url = response.geturl()
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
    title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else final_url
    image_urls: list[str] = []
    for match in re.finditer(r"<img[^>]+(?:src|data-src)=['\"]([^'\"]+)['\"]", html, flags=re.I):
        src = match.group(1)
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            from urllib.parse import urljoin

            src = urljoin(final_url, src)
        if src.startswith("http") and src not in image_urls:
            image_urls.append(src)
    return {"url": final_url, "title": title[:160], "imageUrls": image_urls[:24], "textLength": len(re.sub(r"<[^>]+>", " ", html))}


class Handler(BaseHTTPRequestHandler):
    server_version = "DraftReFormat/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/health":
            json_response(self, {"ok": True, "model": QWEN_MODEL, "configured": bool(os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("QWEN_API_KEY"))})
            return
        path = self.path.split("?", 1)[0]
        if path == "/":
            path = "/index.html"
        file_path = (PUBLIC / path.lstrip("/")).resolve()
        if not str(file_path).startswith(str(PUBLIC.resolve())) or not file_path.is_file():
            json_response(self, {"error": "Not found"}, 404)
            return
        content_type = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml"}.get(file_path.suffix, "application/octet-stream")
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:  # noqa: N802
        try:
            payload = read_json(self)
            if self.path == "/api/segment":
                image = str(payload.get("image", ""))
                if not image.startswith("data:image/"):
                    raise ValueError("需要一个图片 data URL")
                regions, source = call_qwen(image, str(payload.get("hint", "")))
                json_response(self, {"regions": regions, "source": source, "model": QWEN_MODEL})
                return
            if self.path == "/api/import-url":
                result = import_url(str(payload.get("url", "")))
                json_response(self, result)
                return
            if self.path == "/api/proxy-image":
                url = str(payload.get("url", ""))
                if not re.match(r"^https?://", url, flags=re.I):
                    raise ValueError("仅支持 http:// 或 https:// 图片地址")
                request = urllib.request.Request(url, headers={"User-Agent": "DraftReFormat/1.0"})
                with urllib.request.urlopen(request, timeout=20) as response:
                    content_type = response.headers.get_content_type() or "image/jpeg"
                    if not content_type.startswith("image/"):
                        raise ValueError("该地址不是图片资源")
                    content = response.read(8_000_000)
                if not content:
                    raise ValueError("图片内容为空")
                data_url = f"data:{content_type};base64,{base64.b64encode(content).decode('ascii')}"
                json_response(self, {"data": data_url})
                return
            json_response(self, {"error": "Not found"}, 404)
        except Exception as exc:  # keep UI errors readable
            json_response(self, {"error": str(exc)}, 400)


def main() -> None:
    PUBLIC.mkdir(exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Draft ReFormat running at http://{HOST}:{PORT}")
    print(f"Qwen model: {QWEN_MODEL} | API key configured: {bool(os.environ.get('DASHSCOPE_API_KEY') or os.environ.get('QWEN_API_KEY'))}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
