"""Draft ReFormat local server.

The server deliberately uses only the Python standard library so the project can
run on a fresh Python installation.  The browser does the visual editing; this
process only brokers Qwen Vision calls and imports basic web page metadata.
"""

from __future__ import annotations

import base64
import json
import math
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
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:  # Pillow is optional for the offline demo, required for coordinate hints.
    Image = ImageDraw = ImageFont = ImageOps = None


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
QWEN_MODEL = os.environ.get("QWEN_MODEL", "qwen3.8-flash")
QWEN_ENDPOINT = os.environ.get(
    "QWEN_ENDPOINT",
    "https://ws-yqr3lqq5xyjbxf30.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions",
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
            "polygon": [[7, 6], [93, 6], [93, 20], [7, 20]],
            "confidence": 0.82,
            "group": "A",
            "description": "检测到的主标题或题干区域",
        },
        {
            "id": "region-2",
            "label": "正文说明",
            "kind": "text",
            "polygon": [[8, 23], [92, 23], [92, 48], [8, 48]],
            "confidence": 0.76,
            "group": "A",
            "description": "连贯文字段落，建议作为一个语义块",
        },
        {
            "id": "region-3",
            "label": "图表 / 图片",
            "kind": "image",
            "polygon": [[10, 53], [48, 53], [48, 83], [10, 83]],
            "confidence": 0.71,
            "group": "B",
            "description": "图像、插图或数据图表",
        },
        {
            "id": "region-4",
            "label": "公式 / 结构式",
            "kind": "chemistry",
            "polygon": [[53, 55], [90, 55], [90, 79], [53, 79]],
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


def _overlay_font(size: int) -> Any:
    """Load a legible font without making one OS font a hard dependency."""

    for name in ("DejaVuSans.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size=size)
        except (OSError, AttributeError):
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _draw_candidate_boundaries(
    canvas: Any,
    proposal: list[dict[str, Any]],
    content_box: tuple[int, int, int, int],
) -> None:
    """Draw polygon boundaries, holes, and IDs over one source image.

    Rectangles are deliberately never painted here. They are only derived
    internally for cropping and layout compatibility; the model sees the
    actual polygon boundary as the sole region outline.
    """

    draw = ImageDraw.Draw(canvas)
    left, top, right, bottom = content_box
    width, height = max(1, right - left), max(1, bottom - top)
    line_width = max(3, round(max(width, height) / 600))
    font = _overlay_font(max(13, line_width * 4))

    def point(px: Any, py: Any) -> tuple[int, int]:
        return (
            left + round(width * max(0, min(100, float(px))) / 100),
            top + round(height * max(0, min(100, float(py))) / 100),
        )

    for index, region in enumerate(proposal[:80]):
        try:
            deleting = str(region.get("editAction") or "").lower() == "delete"
            polygon_color = (224, 45, 55) if deleting else (155, 45, 220)
            raw_polygon = region.get("polygon")
            if not isinstance(raw_polygon, list) or len(raw_polygon) < 3:
                continue
            polygon = [point(raw_point[0], raw_point[1]) for raw_point in raw_polygon if isinstance(raw_point, (list, tuple)) and len(raw_point) >= 2]
            if len(polygon) < 3:
                continue
            draw.line(polygon + [polygon[0]], fill=polygon_color, width=line_width, joint="curve")
            x0, y0 = polygon[0]

            for hole in region.get("holes") or []:
                if not isinstance(hole, dict) or not isinstance(hole.get("polygon"), list) or len(hole["polygon"]) < 3:
                    continue
                hole_polygon = [point(raw_point[0], raw_point[1]) for raw_point in hole["polygon"] if isinstance(raw_point, (list, tuple)) and len(raw_point) >= 2]
                if len(hole_polygon) >= 3:
                    draw.line(hole_polygon + [hole_polygon[0]], fill=(245, 126, 24), width=line_width, joint="curve")

            label = str(region.get("id") or f"r{index + 1}")
            group = str(region.get("group") or "")
            suffix = " DELETE" if deleting else " POLY"
            tag = f"{label}{' / ' + group if group else ''}{suffix}"
            text_box = draw.textbbox((0, 0), tag, font=font, stroke_width=1)
            tag_width = text_box[2] - text_box[0] + 10
            tag_height = text_box[3] - text_box[1] + 8
            tag_x = max(left, min(right - tag_width, x0))
            tag_y = y0 - tag_height if y0 - tag_height >= top else min(bottom - tag_height, y0 + line_width)
            draw.text((tag_x + 2, tag_y + 2), tag, font=font, fill="white", stroke_width=2, stroke_fill=polygon_color)
        except (TypeError, ValueError):
            continue


def _coordinate_review_canvas(source: Any) -> tuple[Any, tuple[int, int, int, int]]:
    """Place an enlarged image inside external 0–100 coordinate axes."""

    width, height = source.size
    axis_font = _overlay_font(max(16, round(max(width, height) / 110)))
    pad_left = max(92, round(width * 0.045))
    pad_top = max(70, round(height * 0.04))
    pad_right = max(42, round(width * 0.02))
    pad_bottom = max(50, round(height * 0.025))
    canvas = Image.new("RGB", (width + pad_left + pad_right, height + pad_top + pad_bottom), "white")
    canvas.paste(source, (pad_left, pad_top))
    draw = ImageDraw.Draw(canvas)
    x0, y0, x1, y1 = pad_left, pad_top, pad_left + width, pad_top + height
    axis_color = (42, 114, 181)
    axis_width = max(3, round(max(width, height) / 900))
    draw.rectangle((x0, y0, x1, y1), outline=axis_color, width=axis_width)
    axis_y = y0 - max(24, pad_top // 3)
    axis_x = x0 - max(28, pad_left // 3)
    draw.line((x0, axis_y, x1, axis_y), fill=axis_color, width=axis_width)
    draw.line((axis_x, y0, axis_x, y1), fill=axis_color, width=axis_width)
    for index in range(11):
        px = x0 + round(width * index / 10)
        py = y0 + round(height * index / 10)
        label = str(index * 10)
        draw.line((px, axis_y - 6, px, axis_y + 6), fill=axis_color, width=axis_width)
        label_box = draw.textbbox((0, 0), label, font=axis_font)
        label_width = label_box[2] - label_box[0]
        draw.text((px - label_width / 2, max(1, axis_y - pad_top // 2)), label, font=axis_font, fill=(23, 78, 128))
        draw.line((axis_x - 6, py, axis_x + 6, py), fill=axis_color, width=axis_width)
        draw.text((max(1, axis_x - pad_left * 0.55), py - 8), label, font=axis_font, fill=(23, 78, 128))
    draw.text((x1 + 8, axis_y - 10), "X", font=axis_font, fill=(23, 78, 128))
    draw.text((axis_x - 8, y1 + 8), "Y", font=axis_font, fill=(23, 78, 128))
    return canvas, (x0, y0, x1, y1)


def _encode_review_image(image: Any) -> str:
    output = BytesIO()
    image.save(output, format="JPEG", quality=95, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def make_supervision_images(image_data_url: str, proposal: list[dict[str, Any]]) -> list[str]:
    """Create exactly two framed candidate views for the supervisor.

    Image 1 retains a compact source view with all candidate polygon boundaries.
    Image 2 enlarges the source and adds external numeric coordinates while
    repeating the same polygon/hole overlays.
    """

    if Image is None:
        raise RuntimeError("Pillow is required to draw supervision boundaries")
    try:
        _, encoded = image_data_url.split(",", 1)
        source = Image.open(BytesIO(base64.b64decode(encoded)))
        source = ImageOps.exif_transpose(source).convert("RGB") if ImageOps else source.convert("RGB")
        max_dimension = max(1, source.width, source.height)
        compact_scale = min(1.0, 1800 / max_dimension)
        enlarged_scale = min(2.0, 3200 / max_dimension)

        def resized(scale: float) -> Any:
            target = (max(1, round(source.width * scale)), max(1, round(source.height * scale)))
            return source.copy() if target == source.size else source.resize(target, Image.Resampling.LANCZOS)

        compact = resized(compact_scale)
        _draw_candidate_boundaries(compact, proposal, (0, 0, compact.width, compact.height))

        enlarged = resized(enlarged_scale)
        coordinate_canvas, content_box = _coordinate_review_canvas(enlarged)
        _draw_candidate_boundaries(coordinate_canvas, proposal, content_box)
        return [_encode_review_image(compact), _encode_review_image(coordinate_canvas)]
    except Exception as exc:
        raise RuntimeError(f"Unable to create supervision boundary images: {exc}") from exc


def make_region_reanalysis_images(image_data_url: str, region: dict[str, Any]) -> tuple[list[str], bool]:
    """Best-effort boundary overlay for a one-region reanalysis request.

    Pillow is optional for running the editor. If it is unavailable (or the
    image format cannot be rendered), send the original image and let the
    prompt's exact polygon coordinates serve as the reference instead.
    """

    if Image is None:
        return [image_data_url], False
    try:
        return make_supervision_images(image_data_url, [region]), True
    except Exception as exc:
        print(f"Reanalysis boundary overlay skipped: {exc}")
        return [image_data_url], False


def qwen_request(
    model_image: str | list[str],
    prompt: str,
    model: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> tuple[dict[str, Any] | list[Any] | None, str | None]:
    """Make one structured request to the configured Qwen vision model.

    Historical turns are deliberately text-only. This preserves the
    segmentation agent's reasoning context without silently re-sending old
    image payloads; only ``model_image`` is attached to the current turn.
    """

    api_key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("QWEN_API_KEY")
    if not api_key:
        return None, "API key is not configured"
    images = [model_image] if isinstance(model_image, str) else model_image
    content = [{"type": "image_url", "image_url": {"url": image}} for image in images]
    content.append({"type": "text", "text": prompt})
    messages = [
        {"role": item["role"], "content": item["content"]}
        for item in (history or [])
        if item.get("role") in {"user", "assistant"} and isinstance(item.get("content"), str)
    ]
    messages.append({"role": "user", "content": content})
    payload = {
        "model": model or QWEN_MODEL,
        "temperature": 0.05,
        "messages": messages,
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
    return """You are a document-layout and semantic-cropping agent. Analyze the supplied draft image and return every independently editable semantic region for downstream cropping and pagination. The geometry contract is polygons only. Trace the actual content silhouette; do not substitute loose bounding rectangles or axis-aligned boxes.

SEGMENTATION RULES
1. Use content-specific polygon regions that fully enclose the content. Include all visible strokes, punctuation, subscripts/superscripts, captions, borders, arrows, chemical bonds, and image edges. Never let a polygon edge touch or cross printed ink. A modest white safety margin is required; avoiding clipped content has priority over tight crops.
2. CHEMICAL EDGE-SAFETY RULE: for every molecule, structural formula, reaction equation, or mechanism, draw the polygon around the complete ink envelope with visible white clearance outside the outermost mark. Aim for at least 1.5% of the original image width on the left/right and 1.5% of its height above/below whenever that whitespace exists; use more clearance for tiny terminal labels. Do not trace tightly around atom labels or bond lines, and do not put vertices on bond endpoints.
3. Preserve every part of chemistry: all atoms and element symbols, implicit/explicit bond ends, charge marks, isotope numbers, stereochemical wedges/dashes, lone-pair dots, ring bonds, curved electron-pushing arrows and arrowheads, reaction arrows and arrowheads, plus/minus signs, reagents, solvent/temperature/pressure/catalyst labels, yield, and detached conditions above or below arrows. Keep the complete reaction sequence/mechanism together as one semantic region; never split at a reaction arrow, intermediate, or step label.
4. Detect text, figures, tables, chemistry, biology, formulas, question parts, and small but meaningful fragments. Do not discard content to reduce region count. Include nearby caption/annotation when it is necessary to interpret the chemical or scientific figure.
5. A circled, crossed-out, or struck-through item is its own deletion region with editAction="delete". A nearby correction or replacement is a separate region. If a large outer region contains an internal deletion area, keep the outer region and represent the excluded area as a polygon in holes. A hole must also leave safety clearance around the ink being removed and must not erase neighboring reaction marks.
6. Every region MUST have a polygon with at least three points. Trace angled, notched, triangular, curved, and irregular outer boundaries with enough vertices to follow their shape, while keeping the safety margin outside all ink; do not default to four-corner boxes. The polygon itself is the complete cutting boundary; do not output any separate rectangular boundary.
7. Regions belonging to one logical question or image-number collection share one group. Deletion and correction regions remain traceable through their group.
8. Ignore coordinate axes, tick marks, numeric labels, decorative lines, headers, footers, page numbers, and blank padding added around the source image.

COORDINATES
The analysis image has an outer blue 0–100 coordinate frame and no interior grid. Treat that frame as an overlay only. Return polygon points as percentages of the original inner image: top-left is (0,0), bottom-right is (100,100), and every point must be in [0,100]. Round polygon points to one decimal place.

USER NOTE
""" + (hint or "None") + """

OUTPUT SPECIFICATION & SCHEMA
Return strict, valid JSON only. Do not use markdown code blocks, comments, or explanatory text. The output must be directly parseable by a standard JSON parser.

{
  "regions": [
    {
      "id": "r1",
      "label": "Reaction Pathway A",
      "kind": "chemistry",
      "polygon": [[12.5,8.2],[28.0,6.8],[46.5,8.2],[42.0,21.0],[39.0,29.7],[15.0,29.7]],
      "group": "Q1",
      "description": "Multi-step synthesis with catalyst labels",
      "editAction": "delete",
      "holes": [{"polygon": [[20.0,15.0],[26.0,14.0],[30.0,16.0],[28.0,20.0],[22.0,21.0]]}]
    }
  ]
}

FIELD CONSTRAINTS
- id is a unique string. label is concise English, at most five words, with no trailing punctuation.
- kind is exactly one of: ["text", "image", "table", "chemistry", "biology", "formula", "other"].
- polygon is required, contains at least three [x,y] pairs, and is the only region boundary. Trace the actual content silhouette rather than defaulting to four-corner boxes. All points are numbers in [0,100].
- group is a logical grouping string. description is optional.
- editAction is optional and, when present, is exactly "keep" or "delete". Omit it unless deletion/correction rules explicitly require it; the default is "keep".
- Do not output x, y, w, h, bbox, or any other boundary fields besides polygon.
- holes is optional; each hole is an object containing a required polygon of at least three absolute original-image [x,y] percentage points. Never use rectangular coordinates for a hole.
- If a field is not applicable, omit it entirely. Never emit null, empty strings, empty arrays, confidence, color, rotation, or any other extra field.
- The response must start with { and end with }, with zero whitespace outside the JSON. Use double quotes, valid UTF-8, and no trailing commas."""


def polygon_area(points: list[list[float]]) -> float:
    return abs(sum(
        float(points[index][0]) * float(points[(index + 1) % len(points)][1])
        - float(points[(index + 1) % len(points)][0]) * float(points[index][1])
        for index in range(len(points))
    )) / 2


def _point_on_segment(point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]) -> bool:
    cross = (point[0] - start[0]) * (end[1] - start[1]) - (point[1] - start[1]) * (end[0] - start[0])
    return (
        abs(cross) < 1e-7
        and min(start[0], end[0]) - 1e-7 <= point[0] <= max(start[0], end[0]) + 1e-7
        and min(start[1], end[1]) - 1e-7 <= point[1] <= max(start[1], end[1]) + 1e-7
    )


def _point_in_polygon(point: tuple[float, float], polygon: list[list[float]]) -> bool:
    inside = False
    for index, raw_start in enumerate(polygon):
        raw_end = polygon[(index + 1) % len(polygon)]
        start = (float(raw_start[0]), float(raw_start[1]))
        end = (float(raw_end[0]), float(raw_end[1]))
        if _point_on_segment(point, start, end):
            return True
        if (start[1] > point[1]) != (end[1] > point[1]):
            crossing_x = (end[0] - start[0]) * (point[1] - start[1]) / (end[1] - start[1]) + start[0]
            if point[0] < crossing_x:
                inside = not inside
    return inside


def _segments_intersect(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float], d: tuple[float, float]) -> bool:
    def orientation(p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    o1, o2, o3, o4 = orientation(a, b, c), orientation(a, b, d), orientation(c, d, a), orientation(c, d, b)
    if o1 * o2 < -1e-9 and o3 * o4 < -1e-9:
        return True
    return (
        (abs(o1) < 1e-9 and _point_on_segment(c, a, b))
        or (abs(o2) < 1e-9 and _point_on_segment(d, a, b))
        or (abs(o3) < 1e-9 and _point_on_segment(a, c, d))
        or (abs(o4) < 1e-9 and _point_on_segment(b, c, d))
    )


def polygon_self_intersects(polygon: list[list[float]]) -> bool:
    for first in range(len(polygon)):
        a = (float(polygon[first][0]), float(polygon[first][1]))
        b_raw = polygon[(first + 1) % len(polygon)]
        b = (float(b_raw[0]), float(b_raw[1]))
        for second in range(first + 1, len(polygon)):
            if second == (first + 1) % len(polygon) or first == (second + 1) % len(polygon):
                continue
            c_raw, d_raw = polygon[second], polygon[(second + 1) % len(polygon)]
            c, d = (float(c_raw[0]), float(c_raw[1])), (float(d_raw[0]), float(d_raw[1]))
            if _segments_intersect(a, b, c, d):
                return True
    return False


def validate_reanalyzed_polygon(candidate: Any) -> list[str]:
    """Validate polygon-only geometry returned by the independent reanalysis."""

    if not valid_polygon_points(candidate):
        return ["The reanalyzed boundary must contain at least three valid percentage points"]
    if polygon_self_intersects(candidate):
        return ["The reanalyzed boundary must not self-intersect"]
    if polygon_area(candidate) <= 1e-8:
        return ["The reanalyzed boundary has no measurable area"]
    return []


def region_reanalysis_prompt(region: dict[str, Any], has_boundary_overlay: bool = True) -> str:
    """Ask Qwen to independently reassess just one selected semantic region."""

    image_note = (
        "The current region boundary is also drawn over the supplied original image(s)."
        if has_boundary_overlay
        else "No image overlay could be rendered; use the exact current polygon coordinates below as the reference boundary."
    )
    return """You are a document and scientific-image region reanalysis agent. Independently reanalyze ONLY the one selected semantic region described below. This is not page segmentation and not a request to split the region into children. Return one corrected polygon for the same semantic object/block, keeping its identity and meaning.

INPUT
The supplied raster is the ORIGINAL uncropped image. """ + image_note + """ Coordinate axes, if present, are an external aid and are not source content. The selected region's existing polygon is given in exact source-image percentage coordinates below.

TASK
Inspect the complete source around the marked region, then return the best polygon for this same semantic region. Reassess every edge independently: correct tight, clipped, or inaccurate edges and include the complete intended content with a modest white safety margin. The corrected polygon may change shape or size as needed; do not return unrelated neighboring content or split the region. Preserve its semantic group as one block.

CHEMISTRY AND SCIENCE COMPLETENESS
For chemical equations, mechanisms, and molecular structures, keep the complete connected expression together. Include every reactant, intermediate, product, atom label, bond endpoint, charge, isotope, sub/superscript, stereochemical mark, reagent/condition, curved electron-pushing arrow, reaction arrow, full arrow shaft and arrowhead, and detached label belonging to the same expression. Never crop or omit an arrow or its arrowhead. For biological diagrams and scientific figures, include all labels and meaningful edges.

COORDINATES AND OUTPUT
Use percentages of the original inner image: top-left (0,0), bottom-right (100,100). Return a polygon, never a rectangle or bbox. Use enough vertices to represent a non-rectangular outline. Return strict JSON only, with exactly one key:
{"polygon":[[12.0,8.0],[30.0,7.0],[48.0,9.0],[45.0,28.0],[15.0,30.0]]}
No x/y/w/h, no extra keys, no nulls, no markdown fences, no explanation.

CURRENT REGION TO REANALYZE
""" + json.dumps(region, ensure_ascii=False)


def model_visible_regions(regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strip editor-only bounds before candidate data is shown to any agent."""

    visible: list[dict[str, Any]] = []
    for region in regions[:80]:
        if not isinstance(region, dict) or not isinstance(region.get("polygon"), list):
            continue
        item: dict[str, Any] = {}
        for key in ("id", "label", "kind", "polygon", "group", "description", "editAction", "confidence"):
            if key in region:
                item[key] = region[key]
        holes = region.get("holes")
        if isinstance(holes, list):
            visible_holes = [
                {"polygon": hole["polygon"]}
                for hole in holes
                if isinstance(hole, dict) and isinstance(hole.get("polygon"), list)
            ]
            if visible_holes:
                item["holes"] = visible_holes
        visible.append(item)
    return visible


def segmentation_revision_prompt(
    current: list[dict[str, Any]],
    issues: list[str],
    supervisor_regions: list[dict[str, Any]],
) -> str:
    """Ask the original segmentation agent to revise a supervised proposal."""

    return """Continue your role as the document-layout and semantic-cropping agent from the conversation history.

You receive exactly two aligned images containing the same current candidate regions:
1. Candidate Boundary Overlay: the original image at a compact scale with every current polygon boundary drawn over the source content.
2. Enlarged Coordinate Boundary Overlay: an enlarged view with the same polygon boundaries plus external numeric 0–100 X/Y axes. There are no interior grid lines.

Every candidate is outlined by one colored polygon and labeled with its region ID and group. Purple polygons are keep candidates; red polygons are deletion candidates; orange polygons are internal holes/cutouts. There are no candidate rectangles or bbox outlines in either image. All colored lines, labels, axes, and outer padding are review overlays, not source content. No separate clean original image is supplied in this revision turn.

Revise the complete region list using the supervisor feedback below. Return every valid region, including unchanged regions; never return a partial diff. Read precise coordinate values from the enlarged coordinate overlay, but measure all percentages against the original inner image, not the enlarged canvas or outer axes. Preserve every content edge and each complete semantic unit. For every chemical structure/equation/mechanism, place the polygon outside the outermost ink with a visible white safety buffer (aim for at least 1.5% of original-image width and height where available); never let a vertex touch a bond, atom label, arrowhead, charge, isotope, stereomark, or condition. Expand clipped/tight chemistry boundaries even if this introduces a small amount of white space. Include every reactant, intermediate, product, bond endpoint, curved/reaction arrowhead, catalyst/reagent/solvent/temperature label, yield, and connected annotation in one complete semantic unit. Keep crossed-out content as a separate delete region, keep nearby corrections separate, and preserve internal deletions as absolute-coordinate polygon holes. Holes around chemical ink also need a white safety buffer and must not remove adjacent content. Use polygons for every region and every hole; never output rectangle fields for regions or holes.

SUPERVISOR ISSUES
""" + json.dumps(issues, ensure_ascii=False) + """

CURRENT SEGMENTATION
""" + json.dumps(model_visible_regions(current), ensure_ascii=False) + """

SUPERVISOR'S CORRECTED REFERENCE
""" + json.dumps(model_visible_regions(supervisor_regions), ensure_ascii=False) + """

OUTPUT SPECIFICATION & SCHEMA
Return strict, valid JSON only. Do not use markdown code blocks, comments, or explanatory text. The output must be directly parseable by a standard JSON parser.

{
  "regions": [
    {
      "id": "r1",
      "label": "Reaction Pathway A",
      "kind": "chemistry",
      "polygon": [[12.5,8.2],[28.0,6.8],[46.5,8.2],[42.0,21.0],[39.0,29.7],[15.0,29.7]],
      "group": "Q1",
      "description": "Multi-step synthesis with catalyst labels",
      "editAction": "delete",
      "holes": [{"polygon": [[20.0,15.0],[26.0,14.0],[30.0,16.0],[28.0,20.0],[22.0,21.0]]}]
    }
  ]
}

FIELD CONSTRAINTS
- id is unique. label is concise English with at most five words and no trailing punctuation.
- kind is exactly one of ["text", "image", "table", "chemistry", "biology", "formula", "other"]. Convert supervisor kinds such as chemical/diagram/annotation to the closest value in this enum.
- polygon is required, contains at least three [x,y] pairs, and is the only region boundary. Trace the actual content silhouette rather than defaulting to four-corner boxes. Every point is a percentage in [0,100] relative to the original inner image. Round points to one decimal place.
- group is a logical grouping string. description is optional.
- editAction is optional and exactly "keep" or "delete" when present. Omit ordinary "keep" values; default is "keep".
- Do not output x, y, w, h, bbox, or any other boundary fields besides polygon.
- holes is optional; each hole contains a polygon with absolute original-image [x,y] percentages. Omit holes when none exist. Never use rectangular coordinates for a hole.
- Omit every inapplicable field. Never emit null, empty strings, empty arrays, confidence, color, rotation, or extra fields.
- The response must start with { and end with }, with zero whitespace outside the JSON. Use double quotes and no trailing commas."""


def supervision_prompt(current: list[dict[str, Any]]) -> str:
    """Build the strict correction prompt used by the supervisor agent."""

    return """You are a production Layout Segmentation QA and Supervisor Agent.

You receive exactly two aligned images containing the same candidate regions:
1. Candidate Boundary Overlay: a compact view of the original image with every candidate polygon drawn over its source content.
2. Enlarged Coordinate Boundary Overlay: a higher-resolution enlarged view with the same candidate polygons plus external numeric 0–100 X/Y axes. There are no interior grid lines.

Each candidate is labeled with its region ID and group and is shown by one colored polygon only. Purple polygons are keep candidates; red polygons are deletion candidates; orange polygons are internal holes/cutouts. There are no candidate rectangles or bbox outlines. All colored lines, labels, axes, and outer padding are review overlays, not document content.

Cross-reference both images. Return the complete corrected set of regions, not a partial diff. Preserve semantic completeness and content-edge completeness: every visible stroke, punctuation mark, caption, chemical bond, arrow, sub/superscript, table border, image edge, and correction must remain inside an appropriate region. A polygon must not touch or cross source ink; leave a visible white safety band inside its perimeter. Do not include overlay lines, IDs, coordinate axes, tick labels, outer padding, decorative lines, headers, footers, or blank whitespace as content.

SUPERVISION RULES
1. Every independently editable/readable item must be represented. Do not omit small captions, question numbers, formulas, or annotations.
2. Keep chemical equations, reaction pathways, mechanisms, arrows, reactants, intermediates, products, conditions, catalysts, and connected labels as one semantically complete block. Never split a mechanism or reaction in the middle. Check each chemistry polygon at high magnification against the original: it must include every atom/element label, implicit or explicit bond endpoint, ring bond, charge, isotope/subscript/superscript, stereochemical wedge/dash, curved arrow and arrowhead, reaction arrow and arrowhead, plus/minus sign, reagent, solvent, temperature/pressure/catalyst label, yield, and detached condition belonging to the sequence. The polygon boundary must sit visibly outside all this ink; target at least 1.5% of original-image width and height as white clearance where possible. If any chemical mark touches or nearly touches an edge, mark revise and expand that polygon. Do not trade completeness for a tight silhouette.
3. A circled, crossed-out, or struck-through item must be a separate region with editAction="delete". A nearby correction or replacement must be a separate region. If an outer region contains an internal deletion, keep the outer region and use an absolute-coordinate polygon in holes.
4. Every region MUST use a polygon as its complete cutting boundary. Follow the visible content silhouette with enough points for angled, curved, or notched shapes, but keep every boundary outside source ink with safety clearance; do not default to four-corner boxes. Every hole MUST also be a polygon and must leave clearance around removed ink without erasing adjacent marks. Never output a rectangle, bbox, or x/y/w/h fields for either regions or holes.
5. Read precise values from the enlarged coordinate overlay, but calculate every polygon point against the original inner image, not the enlarged canvas or its outer axes. Every point is an [x,y] pair in [0,100]. Use at least three points for each region/hole and round points to exactly two decimal places.
6. If status is pass, issues must be []. If status is revise, issues must briefly identify the remaining defects. In both cases regions must be the complete final region list.

CANDIDATE REGIONS
""" + json.dumps(model_visible_regions(current), ensure_ascii=False) + """

OUTPUT SCHEMA & FORMATTING RULES
You MUST output a single valid JSON object matching the exact structure below. Do not use markdown backticks, code blocks, or conversational text. Output only raw JSON.

{
  "status": "revise",
  "issues": ["Boundary clips reaction arrow"],
  "regions": [
    {
      "id": "r1",
      "label": "Reaction Pathway A",
      "kind": "chemical",
      "polygon": [[12.50,8.20],[28.00,6.80],[46.50,8.20],[42.00,21.00],[39.00,29.70],[15.00,29.70]],
      "confidence": 0.95,
      "group": "Q1",
      "description": "Complete reaction with catalyst labels",
      "editAction": "keep",
      "holes": [{"polygon": [[20.00,15.00],[26.00,14.00],[30.00,16.00],[28.00,20.00],[22.00,21.00]]}]
    }
  ]
}

SERIALIZATION CONSTRAINTS
- status is exactly "pass" or "revise". kind is exactly one of ["text","image","formula","table","diagram","chemical","annotation","other"]. editAction is exactly "keep" or "delete". confidence is a number from 0.00 through 1.00.
- Candidate values from the first agent use chemistry/biology; serialize these as chemical/diagram in your response so the output always follows the supervisor enum.
- polygon is required and must contain at least three [x,y] pairs tracing the actual content boundary; do not default to four-corner boxes. It is the only region boundary; never emit x/y/w/h or bbox. holes is optional and, when present, must be an array of objects containing polygon point arrays only. Never encode a hole as x/y/w/h. Omit holes or use null when no internal exclusion is needed; do not emit empty arrays.
- Every region must include id, label, kind, polygon, confidence, group, description, and editAction. Use editAction="keep" for ordinary content and "delete" only for explicit deletion/cross-out content.
- No extra fields. No markdown, comments, explanations, trailing commas, or partial region lists. Escape strings correctly and ensure the result starts with { and ends with }."""


def valid_polygon_points(points: Any) -> bool:
    return (
        isinstance(points, list)
        and len(points) >= 3
        and all(
            isinstance(point, list)
            and len(point) == 2
            and all(
                not isinstance(value, bool)
                and isinstance(value, (int, float))
                and math.isfinite(float(value))
                and 0 <= float(value) <= 100
                for value in point
            )
            for point in points
        )
    )


def validate_segmentation_response(payload: Any) -> list[str]:
    """Enforce polygon-only geometry in both splitter turns."""

    if not isinstance(payload, dict):
        return ["Splitter output must be one JSON object"]
    violations: list[str] = []
    if set(payload) != {"regions"}:
        violations.append("Splitter output must contain only regions")
    regions = payload.get("regions")
    if not isinstance(regions, list) or not regions:
        return violations + ["regions must be a non-empty complete array"]
    if len(regions) > 80:
        violations.append("regions cannot exceed 80 items")
    required = {"id", "label", "kind", "polygon", "group"}
    allowed = required | {"description", "editAction", "holes"}
    kinds = {"text", "image", "table", "chemistry", "biology", "formula", "other"}
    ids: set[str] = set()
    for index, region in enumerate(regions[:80]):
        prefix = f"regions[{index}]"
        if not isinstance(region, dict):
            violations.append(f"{prefix} must be an object")
            continue
        missing = required - set(region)
        extras = set(region) - allowed
        if missing:
            violations.append(f"{prefix} missing: " + ", ".join(sorted(missing)))
        if extras:
            violations.append(f"{prefix} has forbidden or extra fields: " + ", ".join(sorted(extras)))
        for key in ("id", "label", "group"):
            if not isinstance(region.get(key), str) or not region[key].strip():
                violations.append(f"{prefix}.{key} must be a non-empty string")
        if isinstance(region.get("id"), str):
            if region["id"] in ids:
                violations.append(f"{prefix}.id must be unique")
            ids.add(region["id"])
        if region.get("kind") not in kinds:
            violations.append(f"{prefix}.kind is outside the enum")
        if "description" in region and not isinstance(region["description"], str):
            violations.append(f"{prefix}.description must be a string")
        if region.get("editAction") not in {None, "keep", "delete"}:
            violations.append(f"{prefix}.editAction is outside the enum")
        if not valid_polygon_points(region.get("polygon")):
            violations.append(f"{prefix}.polygon must contain valid [x,y] points")
        holes = region.get("holes")
        if holes is not None:
            if not isinstance(holes, list) or not holes:
                violations.append(f"{prefix}.holes must be a non-empty array when present")
            else:
                for hole_index, hole in enumerate(holes):
                    if not isinstance(hole, dict) or set(hole) != {"polygon"} or not valid_polygon_points(hole.get("polygon")):
                        violations.append(f"{prefix}.holes[{hole_index}] must contain only a valid polygon")
    return violations[:12]


def validate_supervision_response(payload: Any) -> list[str]:
    """Return schema violations for the supervisor's strict JSON contract."""

    if not isinstance(payload, dict):
        return ["Supervisor output must be one JSON object"]
    issues: list[str] = []
    allowed_top = {"status", "issues", "regions"}
    extra_top = set(payload) - allowed_top
    if extra_top:
        issues.append("Unexpected top-level fields: " + ", ".join(sorted(extra_top)))
    status = payload.get("status")
    if status not in {"pass", "revise"}:
        issues.append("status must be pass or revise")
    raw_issues = payload.get("issues")
    if not isinstance(raw_issues, list) or any(not isinstance(item, str) for item in raw_issues):
        issues.append("issues must be an array of strings")
    elif status == "pass" and raw_issues:
        issues.append("issues must be empty when status is pass")
    elif status == "revise" and not raw_issues:
        issues.append("issues must describe defects when status is revise")
    regions = payload.get("regions")
    if not isinstance(regions, list) or not regions:
        issues.append("regions must be a non-empty complete array")
        return issues

    required = {"id", "label", "kind", "polygon", "confidence", "group", "description", "editAction"}
    allowed = required | {"holes"}
    kinds = {"text", "image", "formula", "table", "diagram", "chemical", "annotation", "other"}
    for index, region in enumerate(regions[:80]):
        prefix = f"regions[{index}]"
        if not isinstance(region, dict):
            issues.append(f"{prefix} must be an object")
            continue
        missing = required - set(region)
        extras = set(region) - allowed
        if missing:
            issues.append(f"{prefix} missing: " + ", ".join(sorted(missing)))
        if extras:
            issues.append(f"{prefix} has extra fields: " + ", ".join(sorted(extras)))
        for key in ("id", "label", "group", "description"):
            if not isinstance(region.get(key), str) or not region.get(key):
                issues.append(f"{prefix}.{key} must be a non-empty string")
        if region.get("kind") not in kinds:
            issues.append(f"{prefix}.kind is outside the enum")
        if region.get("editAction") not in {"keep", "delete"}:
            issues.append(f"{prefix}.editAction is outside the enum")
        confidence = region.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(float(confidence)) or not 0 <= float(confidence) <= 1:
            issues.append(f"{prefix}.confidence must be between 0 and 1")
        polygon = region.get("polygon")
        if not isinstance(polygon, list) or len(polygon) < 3:
            issues.append(f"{prefix}.polygon must contain at least three points")
        elif not valid_polygon_points(polygon):
            issues.append(f"{prefix}.polygon contains an invalid point")
        holes = region.get("holes")
        if holes is not None and not isinstance(holes, list):
            issues.append(f"{prefix}.holes must be null, omitted, or an array")
        elif isinstance(holes, list):
            if not holes:
                issues.append(f"{prefix}.holes must be null or omitted when empty")
            for hole in holes:
                if not isinstance(hole, dict) or set(hole) != {"polygon"}:
                    issues.append(f"{prefix}.holes contains an invalid object")
                    break
                if not valid_polygon_points(hole.get("polygon")):
                    issues.append(f"{prefix}.holes contains an invalid polygon")
                    break
    return issues[:12]


def revise_regions(
    original_image: str,
    current: list[dict[str, Any]],
    issues: list[str],
    supervisor_regions: list[dict[str, Any]],
    history: list[dict[str, str]],
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Continue the segmentation conversation using only the two overlay views."""

    try:
        revision_images = make_supervision_images(original_image, current)
    except RuntimeError as exc:
        return None, str(exc)
    prompt = segmentation_revision_prompt(current, issues, supervisor_regions)
    parsed, error = qwen_request(revision_images, prompt, history=history)
    if not parsed:
        return None, error or "分割 Agent 修改失败"
    schema_issues = validate_segmentation_response(parsed)
    if schema_issues:
        return None, "分割 Agent 返回了非多边形或无效结构：" + "; ".join(schema_issues[:4])
    proposal = parsed.get("regions", []) if isinstance(parsed, dict) else []
    if not isinstance(proposal, list) or not proposal:
        return None, "分割 Agent 修改结果没有完整 regions"
    revised = normalize_regions(
        proposal,
        precision=1,
        include_confidence=False,
        include_keep_action=False,
    )
    if not revised:
        return None, "分割 Agent 修改结果没有有效区域"
    # Preserve every successful text turn. Old image payloads are intentionally
    # not duplicated; the current turn always receives freshly rendered views.
    history.extend([
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))},
    ])
    return revised, None


def supervise_regions(
    original_image: str,
    proposal: list[dict[str, Any]],
    segmentation_history: list[dict[str, str]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Run supervisor review and splitter revisions, bounded to safe rounds."""

    current = proposal
    audit: list[dict[str, Any]] = []
    splitter_history = list(segmentation_history or [])
    # Keep retrying until the supervisor passes, with a conservative hard cap
    # so a malformed model response cannot create an unbounded bill/loop.
    max_rounds = max(1, min(10, int(os.environ.get("QWEN_SUPERVISOR_ROUNDS", "10"))))
    for round_number in range(1, max_rounds + 1):
        review_prompt = supervision_prompt(current)
        try:
            review_images = make_supervision_images(original_image, current)
        except RuntimeError as exc:
            audit.append({"round": round_number, "status": "error", "issues": [str(exc)]})
            return current, audit, False
        parsed, error = qwen_request(review_images, review_prompt)
        if not parsed:
            audit.append({"round": round_number, "status": "error", "issues": [error or "监督请求失败"]})
            return current, audit, False
        schema_issues = validate_supervision_response(parsed)
        if schema_issues:
            audit.append({"round": round_number, "status": "revise", "issues": schema_issues[:8]})
            continue
        candidate = parsed.get("regions", []) if isinstance(parsed, dict) else []
        corrected = normalize_regions(candidate, precision=2) if isinstance(candidate, list) else []
        status = str(parsed.get("status", "revise")).lower() if isinstance(parsed, dict) else "revise"
        issues = parsed.get("issues", []) if isinstance(parsed, dict) else []
        if not isinstance(issues, list):
            issues = [str(issues)] if issues else []
        clean_issues = [str(item) for item in issues[:8]]
        passed = status == "pass" and not clean_issues and bool(corrected)
        audit.append({"round": round_number, "status": "pass" if passed else "revise", "issues": clean_issues})
        if passed:
            return corrected, audit, True
        if round_number >= max_rounds:
            return corrected or current, audit, False
        revised, revision_error = revise_regions(
            original_image,
            current,
            clean_issues or ["Supervisor requested another complete boundary revision"],
            corrected or current,
            splitter_history,
        )
        if not revised:
            audit[-1]["revisionError"] = revision_error or "分割 Agent 修改失败"
            return corrected or current, audit, False
        current = revised
    return current, audit, False


def prepare_qwen(image_data_url: str, hint: str = "") -> tuple[list[dict[str, Any]], str, dict[str, Any], list[dict[str, str]] | None]:
    """Run the first segmentation request and return a coordinate proposal."""

    api_key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("QWEN_API_KEY")
    if not api_key:
        return heuristic_regions(), "offline", {"status": "offline", "rounds": 0, "issues": ["未配置 API key"]}, None

    model_image = add_coordinate_grid(image_data_url)
    initial_prompt = segmentation_prompt(hint)
    parsed, error = qwen_request(model_image, initial_prompt)
    if not parsed:
        print(f"Qwen request failed, using offline layout: {error}")
        return heuristic_regions(), "offline", {"status": "error", "rounds": 0, "issues": [error or "初次分割失败"]}, None
    schema_issues = validate_segmentation_response(parsed)
    if schema_issues:
        message = "初次分割结果未遵守纯多边形格式：" + "; ".join(schema_issues[:4])
        return heuristic_regions(), "offline", {"status": "error", "rounds": 0, "issues": [message]}, None
    proposal = parsed.get("regions", []) if isinstance(parsed, dict) else []
    if not isinstance(proposal, list) or not proposal:
        return heuristic_regions(), "offline", {"status": "error", "rounds": 0, "issues": ["Qwen response contained no regions"]}, None
    normalized = normalize_regions(
        proposal,
        precision=1,
        include_confidence=False,
        include_keep_action=False,
    )
    if not normalized:
        return heuristic_regions(), "offline", {"status": "error", "rounds": 0, "issues": ["Qwen response contained no valid regions"]}, None
    history = [
        {"role": "user", "content": initial_prompt},
        {"role": "assistant", "content": json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))},
    ]
    return normalized, "qwen-initial", {"status": "pending", "rounds": 0, "audit": []}, history


def call_qwen(image_data_url: str, hint: str = "") -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    """Run segmentation and supervision synchronously for CLI/benchmark callers."""

    regions, source, supervision, segmentation_history = prepare_qwen(image_data_url, hint)
    if source != "qwen-initial" or not segmentation_history:
        return regions, source, supervision
    regions, audit, passed = supervise_regions(image_data_url, regions, segmentation_history)
    return regions, "qwen-supervised", {"status": "pass" if passed else "max-rounds", "rounds": len(audit), "audit": audit}


def start_supervision_job(
    proposal: list[dict[str, Any]],
    original_image: str,
    segmentation_history: list[dict[str, str]],
) -> str:
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
    thread = threading.Thread(
        target=_run_supervision_job,
        args=(job_id, proposal, original_image, segmentation_history),
        daemon=True,
    )
    thread.start()
    return job_id


def _run_supervision_job(
    job_id: str,
    proposal: list[dict[str, Any]],
    original_image: str,
    segmentation_history: list[dict[str, str]],
) -> None:
    try:
        regions, audit, passed = supervise_regions(original_image, proposal, segmentation_history)
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


def normalize_points(raw: Any, precision: int = 2) -> list[list[float]]:
    """Normalize optional polygon points expressed as [x,y] or {x,y}."""

    points: list[list[float]] = []
    if not isinstance(raw, list):
        return points
    for point in raw[:32]:
        try:
            if isinstance(point, dict):
                px, py = point.get("x"), point.get("y")
            elif isinstance(point, (list, tuple)) and len(point) >= 2:
                px, py = point[0], point[1]
            else:
                continue
            points.append([
                round(max(0, min(100, float(px))), precision),
                round(max(0, min(100, float(py))), precision),
            ])
        except (TypeError, ValueError):
            continue
    return points if len(points) >= 3 else []


def normalize_holes(raw: Any, precision: int = 2) -> list[dict[str, Any]]:
    holes: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return holes
    for hole in raw[:24]:
        if not isinstance(hole, dict):
            continue
        points = normalize_points(hole.get("polygon"), precision)
        if len(points) >= 3:
            holes.append({"polygon": points})
    return holes


def normalize_regions(
    regions: list[dict[str, Any]],
    precision: int = 2,
    include_confidence: bool = True,
    include_keep_action: bool = True,
) -> list[dict[str, Any]]:
    """Validate model JSON and convert both agent schemas to editor regions.

    The model-facing contract is polygon-only. Editor x/y/w/h values are
    derived from polygon extrema for crop sizing and compatibility, never read
    as model-provided region geometry. Unknown model keys are discarded.
    """

    kind_map = {
        "text": "text",
        "image": "image",
        "table": "table",
        "chemistry": "chemistry",
        "chemical": "chemical",
        "biology": "biology",
        "diagram": "diagram",
        "annotation": "annotation",
        "formula": "formula",
        "other": "other",
    }
    normalized: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for index, region in enumerate(regions[:80]):
        if not isinstance(region, dict):
            continue
        try:
            raw_polygon = normalize_points(region.get("polygon"), precision)
            if len(raw_polygon) < 3:
                continue
            x = min(point[0] for point in raw_polygon)
            y = min(point[1] for point in raw_polygon)
            right = max(point[0] for point in raw_polygon)
            bottom = max(point[1] for point in raw_polygon)
            w = right - x
            h = bottom - y
            if w <= 0 or h <= 0:
                continue
            raw_kind = str(region.get("kind") or "other").strip().lower()
            region_id = str(region.get("id") or f"r{index + 1}").strip() or f"r{index + 1}"
            if region_id in used_ids:
                suffix = 2
                base_id = region_id
                while f"{base_id}_{suffix}" in used_ids:
                    suffix += 1
                region_id = f"{base_id}_{suffix}"
            used_ids.add(region_id)
            label = str(region.get("label") or "Semantic Region").strip().rstrip(".,;:!?")
            label = " ".join(label.split()[:5])[:80] or "Semantic Region"
            item = {
                "id": region_id,
                "label": label,
                "kind": kind_map.get(raw_kind, "other"),
                "x": round(x, precision),
                "y": round(y, precision),
                "w": round(w, precision),
                "h": round(h, precision),
                "group": str(region.get("group") or f"Q{index + 1}").strip() or f"Q{index + 1}",
            }
            if region.get("description") not in (None, ""):
                item["description"] = str(region["description"])[:120]
            if include_confidence and region.get("confidence") is not None:
                item["confidence"] = round(max(0, min(1, float(region["confidence"]))), 2)
            action = str(region.get("editAction") or "").strip().lower()
            if action == "delete" or (include_keep_action and action == "keep"):
                item["editAction"] = action
            max_x, max_y = x + w, y + h
            item["polygon"] = [
                [round(max(x, min(max_x, px)), precision), round(max(y, min(max_y, py)), precision)]
                for px, py in raw_polygon
            ]
            holes = normalize_holes(region.get("holes"), precision)
            if holes:
                item["holes"] = holes
            normalized.append(item)
        except (TypeError, ValueError):
            continue
    return normalized


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
                regions, source, supervision, segmentation_history = prepare_qwen(image, str(payload.get("hint", "")))
                response: dict[str, Any] = {"regions": regions, "source": source, "model": QWEN_MODEL, "supervision": supervision}
                if source == "qwen-initial" and segmentation_history:
                    job_id = start_supervision_job(regions, image, segmentation_history)
                    response["jobId"] = job_id
                    response["supervision"] = {**supervision, "jobId": job_id}
                json_response(self, response)
                return
            if self.path == "/api/reanalyze-region":
                image = str(payload.get("image", ""))
                current_polygon = payload.get("polygon")
                if not image.startswith("data:image/"):
                    raise ValueError("需要一个图片 data URL")
                if not valid_polygon_points(current_polygon) or polygon_area(current_polygon) <= 1e-8:
                    raise ValueError("当前多边形无效或面积为零")
                region = {
                    "id": "selected-region",
                    "label": str(payload.get("label") or "Selected region"),
                    "kind": str(payload.get("kind") or "other"),
                    "group": str(payload.get("group") or ""),
                    "description": str(payload.get("description") or ""),
                    "editAction": "delete" if payload.get("editAction") == "delete" else "keep",
                    "polygon": current_polygon,
                }
                holes = payload.get("holes")
                if isinstance(holes, list):
                    region["holes"] = [
                        {"polygon": hole["polygon"]}
                        for hole in holes
                        if isinstance(hole, dict) and valid_polygon_points(hole.get("polygon"))
                    ]
                review_images, has_boundary_overlay = make_region_reanalysis_images(image, region)
                parsed, error = qwen_request(
                    review_images,
                    region_reanalysis_prompt(region, has_boundary_overlay=has_boundary_overlay),
                )
                if error:
                    json_response(self, {"error": "原位重分析请求失败：" + error}, 502)
                    return
                if not isinstance(parsed, dict) or set(parsed) != {"polygon"}:
                    json_response(self, {"error": "原位重分析返回格式无效；原分区保持不变"}, 502)
                    return
                issues = validate_reanalyzed_polygon(parsed.get("polygon"))
                if issues:
                    json_response(self, {"error": "原位重分析结果无效：" + issues[0]}, 422)
                    return
                json_response(self, {"polygon": parsed["polygon"], "model": QWEN_MODEL})
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
