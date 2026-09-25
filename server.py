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
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from io import BytesIO
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # Pillow is optional for the offline demo, required for coordinate hints.
    Image = ImageDraw = ImageFont = None


ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
HOST = os.environ.get("DRAFT_HOST", "127.0.0.1")
PORT = int(os.environ.get("DRAFT_PORT", "8765"))


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

# Read Qwen settings after loading the local .env file.  This keeps explicit
# process environment variables authoritative while allowing the normal local
# setup (copying .env.example to .env) to configure the MaaS endpoint.
QWEN_MODEL = os.environ.get("QWEN_MODEL", "qwen3.6-plus")
QWEN_ENDPOINT = os.environ.get(
    "QWEN_ENDPOINT", "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
)
QWEN_REQUEST_TIMEOUT = float(os.environ.get("QWEN_REQUEST_TIMEOUT", "180"))
QWEN_LAST_ERROR = ""
QWEN_JOBS: dict[str, dict[str, Any]] = {}
QWEN_JOBS_LOCK = threading.Lock()


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
    """Expand the image and add numeric coordinate axes, without grid lines.

    The original image is placed inside a white coordinate frame. Only tick
    marks and values (0..100) sit outside the content, so Qwen can read exact
    numeric positions without mistaking grid lines for document content.
    """

    frame_enabled = os.environ.get("QWEN_COORDINATE_FRAME", os.environ.get("QWEN_GRID", "1"))
    if Image is None or frame_enabled.lower() in {"0", "false", "off"}:
        return image_data_url
    try:
        header, encoded = image_data_url.split(",", 1)
        raw = base64.b64decode(encoded)
        source = Image.open(BytesIO(raw)).convert("RGB")
        # Keep payloads manageable while preserving percentage coordinates.
        source.thumbnail((2600, 2600), Image.Resampling.LANCZOS)
        source = source.convert("RGB")
        width, height = source.size
        pad_left, pad_top, pad_right, pad_bottom = 76, 52, 28, 34
        canvas = Image.new("RGB", (width + pad_left + pad_right, height + pad_top + pad_bottom), "white")
        canvas.paste(source, (pad_left, pad_top))
        draw = ImageDraw.Draw(canvas)
        font = ImageFont.load_default()
        x0, y0 = pad_left, pad_top
        x1, y1 = pad_left + width, pad_top + height
        draw.rectangle((x0, y0, x1, y1), outline=(42, 114, 181), width=2)
        # Axes are outside the content; there are deliberately no interior lines.
        draw.line((x0, y0 - 20, x1, y0 - 20), fill=(42, 114, 181), width=2)
        draw.line((x0 - 20, y0, x0 - 20, y1), fill=(42, 114, 181), width=2)
        for index in range(0, 11):
            x = x0 + round(width * index / 10)
            y = y0 + round(height * index / 10)
            label = str(index * 10)
            draw.line((x, y0 - 25, x, y0 - 15), fill=(42, 114, 181), width=2)
            draw.text((x - 7, y0 - 42), label, font=font, fill=(23, 78, 128))
            draw.line((x0 - 25, y, x0 - 15, y), fill=(42, 114, 181), width=2)
            draw.text((x0 - 63, y - 5), label, font=font, fill=(23, 78, 128))
        draw.text((x1 + 5, y0 - 25), "X", font=font, fill=(23, 78, 128))
        draw.text((x0 - 22, y1 + 8), "Y", font=font, fill=(23, 78, 128))
        output = BytesIO()
        canvas.save(output, format="JPEG", quality=94, optimize=True)
        return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")
    except Exception as exc:
        print(f"Grid overlay skipped: {exc}")
        return image_data_url


def qwen_request(model_image: str, prompt: str, model: str | None = None) -> tuple[dict[str, Any] | None, str | None]:
    """Make one structured request to the configured Qwen vision model."""

    api_key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("QWEN_API_KEY")
    if not api_key:
        return None, "API key is not configured"
    payload = {
        "model": model or QWEN_MODEL,
        "temperature": 0.05,
        "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": model_image}}, {"type": "text", "text": prompt}]}],
    }
    request = urllib.request.Request(QWEN_ENDPOINT, data=json.dumps(payload).encode("utf-8"), headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST")
    global QWEN_LAST_ERROR
    try:
        with urllib.request.urlopen(request, timeout=QWEN_REQUEST_TIMEOUT) as response:
            body = json.loads(response.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        QWEN_LAST_ERROR = ""
        return json.loads(clean_json_text(str(content))), None
    except urllib.error.HTTPError as exc:
        # Preserve the provider's machine-readable error without ever exposing
        # the Authorization header or the configured API key.
        detail = ""
        try:
            raw = exc.read().decode("utf-8", "replace")
            payload = json.loads(raw)
            error = payload.get("error", payload) if isinstance(payload, dict) else {}
            if isinstance(error, dict):
                code = error.get("code") or error.get("type")
                message = error.get("message")
                detail = ": ".join(str(value) for value in (code, message) if value)
            if not detail:
                detail = raw[:240]
        except Exception:
            detail = ""
        QWEN_LAST_ERROR = f"HTTP {exc.code}" + (f" {detail}" if detail else "")
        return None, QWEN_LAST_ERROR
    except (urllib.error.URLError, socket.timeout, TimeoutError, KeyError, ValueError, json.JSONDecodeError) as exc:
        QWEN_LAST_ERROR = str(exc)
        return None, QWEN_LAST_ERROR


def segmentation_prompt(hint: str = "") -> str:
    return f"""你是文档版面分析与语义分割专家。请分析这张草稿截图，给出适合后续裁剪、编辑和分页的语义区域。
要求：
1. 这是“裁剪区域”识别，不是给整页画几个大框。每个题号、段落、图表、结构式、公式都要成为独立且紧致的内容块，尽量贴合可见内容，排除周围空白；相邻内容只有在语义上不可分时才合并。
2. 区域用覆盖内容的最小矩形表示；不要切断公式、化学结构式、图注或生物图片，不要让一个框横跨多个无关对象。
3. 文字段落、题目、插图、表格、化学结构式、数学公式、生物图片分别识别；小块也必须保留，不得为了减少数量而丢弃。
4. 同属一个题目/图片编号集合的区域使用相同 group（例如 1、1a、1b 都用 group=\"1\"）。
5. 坐标为相对于原图的百分比 0-100，x/y 是左上角，w/h 是宽高；只输出 JSON，不要 Markdown。
6. label 使用简短中文，kind 只能是 text/image/table/chemistry/biology/formula/other。
7. 过滤页眉、页脚、装饰线和大面积空白；对每个真实内容给出边界，至少保留一个主内容区域。
8. 原图被放在白色坐标框内，外侧只有蓝色坐标轴、刻度和 0..100 数值，没有内部网格线。内容框左上角对应 (0,0)，右下角对应 (100,100)。坐标轴、刻度和白色扩展区不是内容，必须忽略；输出坐标仍对应没有坐标框的原始图片。
用户补充：{hint or '无'}
输出格式：{{\"regions\":[{{\"id\":\"r1\",\"label\":\"...\",\"kind\":\"text\",\"x\":0,\"y\":0,\"w\":20,\"h\":10,\"confidence\":0.92,\"group\":\"1\",\"description\":\"...\"}}]}}"""


def supervise_regions(model_image: str, proposal: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Have Qwen audit and correct the proposal, bounded to three rounds."""

    current = proposal
    audit: list[dict[str, Any]] = []
    # Keep retrying until the supervisor passes, with a conservative hard cap
    # so a malformed model response cannot create an unbounded bill/loop.
    max_rounds = max(1, min(6, int(os.environ.get("QWEN_SUPERVISOR_ROUNDS", "5"))))
    for round_number in range(1, max_rounds + 1):
        review_prompt = f"""你是严格的版面分割监督审校 agent。请检查候选区域是否覆盖图片中所有真实内容，并指出漏块、误合并、边界过松/过紧、截断结构式或错误编号集合。
监督标准：
1. 每个可独立阅读或编辑的内容都必须有一个区域，小图注、化学键、公式、题号不能丢。
2. 区域必须紧贴内容，不能把大块空白或无关内容放入同一个框。
3. 不能切断相互连接的公式、化学结构式、表格、图片和图注。
4. 坐标使用原图百分比 0-100，外侧坐标轴、刻度和白色扩展区不属于内容。
如果不通过，直接给出修正后的完整 regions 数组，而不是只描述问题。只有确实满足标准时 status 才能是 pass。
候选 regions：{json.dumps(current, ensure_ascii=False)}
只输出 JSON：{{\"status\":\"pass\"或\"revise\",\"issues\":[\"...\"],\"regions\":[{{\"id\":\"r1\",\"label\":\"...\",\"kind\":\"text\",\"x\":0,\"y\":0,\"w\":20,\"h\":10,\"confidence\":0.92,\"group\":\"1\",\"description\":\"...\"}}]}}"""
        parsed, error = qwen_request(model_image, review_prompt)
        if not parsed:
            audit.append({"round": round_number, "status": "error", "issues": [error or "监督请求失败"]})
            return current, audit, False
        candidate = parsed.get("regions", []) if isinstance(parsed, dict) else []
        if isinstance(candidate, list) and candidate:
            current = normalize_regions(candidate)
        status = str(parsed.get("status", "revise")).lower() if isinstance(parsed, dict) else "revise"
        issues = parsed.get("issues", []) if isinstance(parsed, dict) else []
        audit.append({"round": round_number, "status": "pass" if status == "pass" else "revise", "issues": [str(item) for item in issues[:8]]})
        if status == "pass":
            return current, audit, True
    return current, audit, False


def prepare_qwen(image_data_url: str, hint: str = "") -> tuple[list[dict[str, Any]], str, dict[str, Any], str | None]:
    """Run the first segmentation request and return a coordinate proposal."""

    api_key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("QWEN_API_KEY")
    if not api_key:
        return heuristic_regions(), "offline", {"status": "offline", "rounds": 0, "issues": ["未配置 API key"]}, None

    model_image = add_coordinate_grid(image_data_url)
    parsed, error = qwen_request(model_image, segmentation_prompt(hint))
    if not parsed:
        print(f"Qwen request failed, using offline layout: {error}")
        return heuristic_regions(), "offline", {"status": "error", "rounds": 0, "issues": [error or "初次分割失败"]}, model_image
    proposal = parsed.get("regions", parsed if isinstance(parsed, list) else [])
    if not isinstance(proposal, list) or not proposal:
        return heuristic_regions(), "offline", {"status": "error", "rounds": 0, "issues": ["Qwen response contained no regions"]}, model_image
    return normalize_regions(proposal), "qwen-initial", {"status": "pending", "rounds": 0, "audit": []}, model_image


def call_qwen(image_data_url: str, hint: str = "") -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    """Run segmentation and supervision synchronously for CLI/benchmark callers."""

    regions, source, supervision, model_image = prepare_qwen(image_data_url, hint)
    if source != "qwen-initial" or not model_image:
        return regions, source, supervision
    regions, audit, passed = supervise_regions(model_image, regions)
    return regions, "qwen-supervised", {"status": "pass" if passed else "max-rounds", "rounds": len(audit), "audit": audit}


def start_supervision_job(model_image: str, proposal: list[dict[str, Any]]) -> str:
    """Continue supervision in the background so multiple jobs can run concurrently."""

    job_id = f"segment-{uuid.uuid4().hex}"
    with QWEN_JOBS_LOCK:
        if len(QWEN_JOBS) > 100:
            oldest = next(iter(QWEN_JOBS))
            QWEN_JOBS.pop(oldest, None)
        QWEN_JOBS[job_id] = {
            "status": "pending",
            "regions": normalize_regions(proposal),
            "supervision": {"status": "pending", "rounds": 0, "audit": []},
        }
    thread = threading.Thread(target=_run_supervision_job, args=(job_id, model_image, proposal), daemon=True)
    thread.start()
    return job_id


def _run_supervision_job(job_id: str, model_image: str, proposal: list[dict[str, Any]]) -> None:
    try:
        regions, audit, passed = supervise_regions(model_image, proposal)
        status = "pass" if passed else "max-rounds"
        if audit and audit[-1].get("status") == "error":
            status = "error"
        result = {"status": status, "rounds": len(audit), "audit": audit}
        with QWEN_JOBS_LOCK:
            if job_id in QWEN_JOBS:
                QWEN_JOBS[job_id].update({"status": "complete", "regions": regions, "supervision": result})
    except Exception as exc:
        with QWEN_JOBS_LOCK:
            if job_id in QWEN_JOBS:
                QWEN_JOBS[job_id].update({
                    "status": "complete",
                    "supervision": {"status": "error", "rounds": 0, "audit": [{"status": "error", "issues": [str(exc)]}]},
                })


def get_supervision_job(job_id: str) -> dict[str, Any] | None:
    with QWEN_JOBS_LOCK:
        job = QWEN_JOBS.get(job_id)
        return dict(job) if job else None


def normalize_regions(regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kinds = {"text", "image", "table", "chemistry", "biology", "formula", "other"}
    normalized: list[dict[str, Any]] = []
    for index, region in enumerate(regions[:80]):
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
            json_response(self, {"ok": True, "model": QWEN_MODEL, "configured": bool(os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("QWEN_API_KEY")), "lastQwenError": QWEN_LAST_ERROR or None})
            return
        parsed_url = urllib.parse.urlsplit(self.path)
        if parsed_url.path == "/api/segment-status":
            job_id = urllib.parse.parse_qs(parsed_url.query).get("jobId", [""])[0]
            job = get_supervision_job(job_id)
            if not job:
                json_response(self, {"error": "分析任务不存在或已过期"}, 404)
                return
            json_response(self, {"jobId": job_id, **job})
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
                regions, source, supervision, model_image = prepare_qwen(image, str(payload.get("hint", "")))
                response: dict[str, Any] = {"regions": regions, "source": source, "model": QWEN_MODEL, "supervision": supervision}
                if source == "qwen-initial" and model_image:
                    job_id = start_supervision_job(model_image, regions)
                    response["jobId"] = job_id
                    response["supervision"] = {**supervision, "jobId": job_id}
                json_response(self, response)
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
