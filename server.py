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


def make_candidate_sheet(image_data_url: str, proposal: list[dict[str, Any]]) -> str | None:
    """Create a compact contact sheet of candidate crops for the supervisor."""

    if Image is None:
        return None
    try:
        _, encoded = image_data_url.split(",", 1)
        source = Image.open(BytesIO(base64.b64decode(encoded))).convert("RGB")
        cards: list[tuple[str, Image.Image]] = []
        for region in proposal[:40]:
            x = max(0, min(100, float(region.get("x", 0))))
            y = max(0, min(100, float(region.get("y", 0))))
            w = max(1, min(100 - x, float(region.get("w", 1))))
            h = max(1, min(100 - y, float(region.get("h", 1))))
            left = round(source.width * x / 100)
            top = round(source.height * y / 100)
            right = max(left + 1, round(source.width * (x + w) / 100))
            bottom = max(top + 1, round(source.height * (y + h) / 100))
            crop = source.crop((left, top, right, bottom))
            crop.thumbnail((280, 180), Image.Resampling.LANCZOS)
            cards.append((str(region.get("id") or len(cards) + 1), crop.copy()))
        if not cards:
            return None
        columns = 3
        card_width, card_height = 320, 220
        sheet = Image.new("RGB", (columns * card_width, ((len(cards) + columns - 1) // columns) * card_height), "white")
        draw = ImageDraw.Draw(sheet)
        for index, (label, crop) in enumerate(cards):
            x0 = (index % columns) * card_width
            y0 = (index // columns) * card_height
            draw.rectangle((x0, y0, x0 + card_width - 1, y0 + card_height - 1), outline=(190, 198, 210), width=2)
            draw.text((x0 + 8, y0 + 6), label, fill=(30, 80, 130))
            sheet.paste(crop, (x0 + (card_width - crop.width) // 2, y0 + 30))
        output = BytesIO()
        sheet.save(output, format="JPEG", quality=88, optimize=True)
        return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")
    except Exception as exc:
        print(f"Candidate sheet skipped: {exc}")
        return None


def qwen_request(model_image: str | list[str], prompt: str, model: str | None = None) -> tuple[dict[str, Any] | list[Any] | None, str | None]:
    """Make one structured request to the configured Qwen vision model."""

    api_key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("QWEN_API_KEY")
    if not api_key:
        return None, "API key is not configured"
    images = [model_image] if isinstance(model_image, str) else model_image
    content = [{"type": "image_url", "image_url": {"url": image}} for image in images]
    content.append({"type": "text", "text": prompt})
    payload = {
        "model": model or QWEN_MODEL,
        "temperature": 0.05,
        "messages": [{"role": "user", "content": content}],
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
    return """You are a document-layout and semantic-cropping agent. Analyze the supplied draft image and return every independently editable semantic region for downstream cropping and pagination.

SEGMENTATION RULES
1. Use tight, content-specific regions. Include all visible strokes, punctuation, subscripts/superscripts, captions, borders, arrows, chemical bonds, and image edges. Do not clip content and do not add large blank margins.
2. Keep a complete chemical reaction, mechanism, arrow sequence, reactants, intermediates, products, conditions, catalysts, and connected annotations together. Never split a chemically or semantically indivisible unit.
3. Detect text, figures, tables, chemistry, biology, formulas, question parts, and small but meaningful fragments. Do not discard content to reduce region count.
4. A boxed, circled, crossed-out, or struck-through item is its own deletion region with editAction="delete". A nearby correction or replacement is a separate region. If a large outer region contains an internal deletion box, keep the outer region and represent the deleted area in holes.
5. Use polygon for triangular, wedge-shaped, or otherwise irregular content when a rectangle would include unrelated material. Always include the enclosing x/y/w/h.
6. Regions belonging to one logical question or image-number collection share one group. Deletion and correction regions remain traceable through their group.
7. Ignore coordinate axes, tick marks, numeric labels, decorative lines, headers, footers, page numbers, and blank padding added around the source image.

COORDINATES
The analysis image has an outer blue 0–100 coordinate frame and no interior grid. Treat that frame as an overlay only. Return x, y, w, h and polygon points as percentages of the original inner image: top-left is (0,0), bottom-right is (100,100), and x+w/y+h must not exceed 100. Round x/y/w/h and polygon points to one decimal place.

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
      "x": 12.5,
      "y": 8.2,
      "w": 34.0,
      "h": 21.5,
      "group": "Q1",
      "description": "Multi-step synthesis with catalyst labels",
      "editAction": "delete",
      "polygon": [[12.5,8.2],[46.5,8.2],[42.0,29.7],[15.0,29.7]],
      "holes": [{"x": 20.0, "y": 15.0, "w": 10.0, "h": 5.0}]
    }
  ]
}

FIELD CONSTRAINTS
- id is a unique string. label is concise English, at most five words, with no trailing punctuation.
- kind is exactly one of: ["text", "image", "table", "chemistry", "biology", "formula", "other"].
- x, y, w, h are numbers in [0,100], with x+w<=100 and y+h<=100.
- group is a logical grouping string. description is optional.
- editAction is optional and, when present, is exactly "keep" or "delete". Omit it unless deletion/correction rules explicitly require it; the default is "keep".
- polygon is optional, contains at least three [x,y] percentage pairs, and should be omitted for a sufficiently rectangular region.
- holes is optional; each hole is an object with absolute original-image x/y/w/h percentages and should be omitted when there is no internal exclusion.
- If a field is not applicable, omit it entirely. Never emit null, empty strings, empty arrays, confidence, color, rotation, or any other extra field.
- The response must start with { and end with }, with zero whitespace outside the JSON. Use double quotes, valid UTF-8, and no trailing commas."""


def supervision_prompt(current: list[dict[str, Any]]) -> str:
    """Build the strict correction prompt used by the supervisor agent."""

    return """You are a production Layout Segmentation QA and Supervisor Agent.

You receive three aligned images:
1. Original Image: the unmodified source document.
2. Analysis Overlay: the source with an outer numeric 0–100 coordinate frame and no interior grid.
3. Candidate Block Contact Map: candidate crops labeled by region ID.

Cross-reference all three images. Return the complete corrected set of regions, not a partial diff. Preserve semantic completeness and content-edge completeness: every visible stroke, punctuation mark, caption, chemical bond, arrow, sub/superscript, table border, image edge, and correction must remain inside an appropriate region. Do not include coordinate axes, tick labels, overlay padding, decorative lines, headers, footers, or blank whitespace.

SUPERVISION RULES
1. Every independently editable/readable item must be represented. Do not omit small captions, question numbers, formulas, or annotations.
2. Keep chemical equations, reaction pathways, mechanisms, arrows, reactants, intermediates, products, conditions, catalysts, and connected labels as one semantically complete block. Never split a mechanism or reaction in the middle.
3. A boxed, circled, crossed-out, or struck-through item must be a separate region with editAction="delete". A nearby correction or replacement must be a separate region. If an outer region contains an internal deletion, keep the outer region and use absolute original-image coordinates in holes.
4. Use polygon for triangular or irregular content when a rectangle would include unrelated material. The bounding box must still fully contain the content.
5. Coordinates are percentages of the ORIGINAL image, not the overlay. Enforce 0<=x,y,w,h<=100, x+w<=100, y+h<=100. Round x/y/w/h to exactly two decimal places; polygon points and hole coordinates are also percentages.
6. If status is pass, issues must be []. If status is revise, issues must briefly identify the remaining defects. In both cases regions must be the complete final region list.

CANDIDATE REGIONS
""" + json.dumps(current, ensure_ascii=False) + """

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
      "x": 12.50,
      "y": 8.20,
      "w": 34.00,
      "h": 21.50,
      "confidence": 0.95,
      "group": "Q1",
      "description": "Complete reaction with catalyst labels",
      "editAction": "keep",
      "polygon": null,
      "holes": null
    }
  ]
}

SERIALIZATION CONSTRAINTS
- status is exactly "pass" or "revise". kind is exactly one of ["text","image","formula","table","diagram","chemical","annotation","other"]. editAction is exactly "keep" or "delete". confidence is a number from 0.00 through 1.00.
- Candidate values from the first agent use chemistry/biology; serialize these as chemical/diagram in your response so the output always follows the supervisor enum.
- polygon and holes are conditional: omit them, or use null, when not needed. Do not emit empty arrays for these fields.
- Every region must include id, label, kind, x, y, w, h, confidence, group, description, and editAction. Use editAction="keep" for ordinary content and "delete" only for explicit deletion/cross-out content.
- No extra fields. No markdown, comments, explanations, trailing commas, or partial region lists. Escape strings correctly and ensure the result starts with { and ends with }."""


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

    required = {"id", "label", "kind", "x", "y", "w", "h", "confidence", "group", "description", "editAction"}
    allowed = required | {"polygon", "holes"}
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
        coordinates: dict[str, float] = {}
        for key in ("x", "y", "w", "h"):
            value = region.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                issues.append(f"{prefix}.{key} must be a finite number")
                continue
            coordinates[key] = float(value)
            if not 0 <= coordinates[key] <= 100:
                issues.append(f"{prefix}.{key} is outside 0-100")
        if len(coordinates) == 4 and (coordinates["x"] + coordinates["w"] > 100 or coordinates["y"] + coordinates["h"] > 100):
            issues.append(f"{prefix} bounding box exceeds the original image")
        polygon = region.get("polygon")
        if polygon is not None and (not isinstance(polygon, list) or len(polygon) < 3):
            issues.append(f"{prefix}.polygon must be null, omitted, or contain at least three points")
        elif isinstance(polygon, list):
            for point in polygon:
                if not isinstance(point, list) or len(point) != 2 or any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or not 0 <= float(value) <= 100 for value in point):
                    issues.append(f"{prefix}.polygon contains an invalid point")
                    break
        holes = region.get("holes")
        if holes is not None and not isinstance(holes, list):
            issues.append(f"{prefix}.holes must be null, omitted, or an array")
        elif isinstance(holes, list):
            if not holes:
                issues.append(f"{prefix}.holes must be null or omitted when empty")
            for hole in holes:
                if not isinstance(hole, dict) or set(hole) != {"x", "y", "w", "h"}:
                    issues.append(f"{prefix}.holes contains an invalid object")
                    break
                try:
                    hx, hy, hw, hh = (float(hole[key]) for key in ("x", "y", "w", "h"))
                    if not all(math.isfinite(value) and 0 <= value <= 100 for value in (hx, hy, hw, hh)) or hx + hw > 100 or hy + hh > 100:
                        issues.append(f"{prefix}.holes contains out-of-range coordinates")
                        break
                except (TypeError, ValueError):
                    issues.append(f"{prefix}.holes coordinates must be numbers")
                    break
    return issues[:12]


def supervise_regions(model_image: str, proposal: list[dict[str, Any]], original_image: str | None = None, candidate_sheet: str | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Have Qwen audit and correct the proposal, bounded to a safe number of rounds."""

    current = proposal
    audit: list[dict[str, Any]] = []
    # Keep retrying until the supervisor passes, with a conservative hard cap
    # so a malformed model response cannot create an unbounded bill/loop.
    max_rounds = max(1, min(6, int(os.environ.get("QWEN_SUPERVISOR_ROUNDS", "5"))))
    for round_number in range(1, max_rounds + 1):
        review_prompt = supervision_prompt(current)
        review_images = [image for image in (original_image, model_image, candidate_sheet) if image] if original_image else model_image
        parsed, error = qwen_request(review_images, review_prompt)
        if not parsed:
            audit.append({"round": round_number, "status": "error", "issues": [error or "监督请求失败"]})
            return current, audit, False
        schema_issues = validate_supervision_response(parsed)
        if schema_issues:
            audit.append({"round": round_number, "status": "revise", "issues": schema_issues[:8]})
            continue
        candidate = parsed.get("regions", []) if isinstance(parsed, dict) else []
        if isinstance(candidate, list) and candidate:
            corrected = normalize_regions(candidate, precision=2)
            if corrected:
                current = corrected
        status = str(parsed.get("status", "revise")).lower() if isinstance(parsed, dict) else "revise"
        issues = parsed.get("issues", []) if isinstance(parsed, dict) else []
        if not isinstance(issues, list):
            issues = [str(issues)] if issues else []
        clean_issues = [str(item) for item in issues[:8]]
        passed = status == "pass" and not clean_issues and bool(current)
        audit.append({"round": round_number, "status": "pass" if passed else "revise", "issues": clean_issues})
        if passed:
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
    proposal = parsed.get("regions", []) if isinstance(parsed, dict) else []
    if not isinstance(proposal, list) or not proposal:
        return heuristic_regions(), "offline", {"status": "error", "rounds": 0, "issues": ["Qwen response contained no regions"]}, model_image
    normalized = normalize_regions(
        proposal,
        precision=1,
        include_confidence=False,
        include_keep_action=False,
    )
    if not normalized:
        return heuristic_regions(), "offline", {"status": "error", "rounds": 0, "issues": ["Qwen response contained no valid regions"]}, model_image
    return normalized, "qwen-initial", {"status": "pending", "rounds": 0, "audit": []}, model_image


def call_qwen(image_data_url: str, hint: str = "") -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    """Run segmentation and supervision synchronously for CLI/benchmark callers."""

    regions, source, supervision, model_image = prepare_qwen(image_data_url, hint)
    if source != "qwen-initial" or not model_image:
        return regions, source, supervision
    regions, audit, passed = supervise_regions(model_image, regions, image_data_url, make_candidate_sheet(image_data_url, regions))
    return regions, "qwen-supervised", {"status": "pass" if passed else "max-rounds", "rounds": len(audit), "audit": audit}


def start_supervision_job(model_image: str, proposal: list[dict[str, Any]], original_image: str) -> str:
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
    thread = threading.Thread(target=_run_supervision_job, args=(job_id, model_image, proposal, original_image), daemon=True)
    thread.start()
    return job_id


def _run_supervision_job(job_id: str, model_image: str, proposal: list[dict[str, Any]], original_image: str) -> None:
    try:
        regions, audit, passed = supervise_regions(model_image, proposal, original_image, make_candidate_sheet(original_image, proposal))
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
        if isinstance(hole, dict) and all(key in hole for key in ("x", "y", "w", "h")):
            try:
                x = max(0, min(100, float(hole["x"])))
                y = max(0, min(100, float(hole["y"])))
                w = max(0, min(100 - x, float(hole["w"])))
                h = max(0, min(100 - y, float(hole["h"])))
                if w and h:
                    holes.append({
                        "x": round(x, precision),
                        "y": round(y, precision),
                        "w": round(w, precision),
                        "h": round(h, precision),
                    })
            except (TypeError, ValueError):
                continue
    return holes


def normalize_regions(
    regions: list[dict[str, Any]],
    precision: int = 2,
    include_confidence: bool = True,
    include_keep_action: bool = True,
) -> list[dict[str, Any]]:
    """Validate model JSON and convert both agent schemas to editor regions.

    The segmentation agent uses chemistry/biology while the supervisor uses
    chemical/diagram/annotation. Both documented enums are preserved so the
    API output continues to match the producing agent's schema. Unknown keys
    are intentionally discarded.
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
            bbox = region.get("bbox") if isinstance(region.get("bbox"), list) else None
            if bbox and len(bbox) >= 4:
                raw_x, raw_y = bbox[0], bbox[1]
                raw_w, raw_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            elif all(key in region for key in ("x", "y", "w", "h")):
                raw_x, raw_y, raw_w, raw_h = (region[key] for key in ("x", "y", "w", "h"))
            else:
                continue
            scale = 0.1 if max(abs(float(raw_x or 0)), abs(float(raw_y or 0)), abs(float(raw_w or 0)), abs(float(raw_h or 0))) > 100 else 1
            x = max(0, min(100, float(raw_x) * scale))
            y = max(0, min(100, float(raw_y) * scale))
            w = min(100 - x, float(raw_w) * scale)
            h = min(100 - y, float(raw_h) * scale)
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
            polygon = normalize_points(region.get("polygon"), precision)
            if polygon:
                max_x, max_y = x + w, y + h
                item["polygon"] = [
                    [round(max(x, min(max_x, px)), precision), round(max(y, min(max_y, py)), precision)]
                    for px, py in polygon
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
                regions, source, supervision, model_image = prepare_qwen(image, str(payload.get("hint", "")))
                response: dict[str, Any] = {"regions": regions, "source": source, "model": QWEN_MODEL, "supervision": supervision}
                if source == "qwen-initial" and model_image:
                    job_id = start_supervision_job(model_image, regions, image)
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
