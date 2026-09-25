"""Small, safe Qwen model comparison for semantic crop detection.

Run after installing Pillow:
    python benchmark_qwen.py

The script never prints the API key. It reports availability, latency, JSON
validity, region count, and coordinate completeness for each candidate model.
"""

from __future__ import annotations

import base64
import json
import time
from io import BytesIO

import server


MODELS = [
    # These are the model IDs exposed by the configured MaaS workspace.
    "qwen3.6-plus",
    "qwen3.6-flash",
    "qwen3-vl-plus",
    "qwen3-vl-flash",
    "qwen-vl-max",
    "qwen-vl-plus",
    "qwen2.5-vl-72b-instruct",
    "qwen2.5-vl-32b-instruct",
]


def test_image() -> str:
    if server.Image is None:
        raise RuntimeError("Pillow is required: python -m pip install -r requirements.txt")
    image = server.Image.new("RGB", (1200, 1500), "white")
    draw = server.ImageDraw.Draw(image)
    draw.rectangle((80, 80, 1120, 250), outline=(60, 60, 80), width=4)
    draw.text((110, 120), "综合练习 1", fill=(20, 20, 30))
    draw.text((110, 190), "请阅读材料并完成问题。", fill=(80, 80, 100))
    draw.rectangle((90, 360, 560, 900), outline=(40, 130, 100), width=4)
    draw.ellipse((160, 500, 490, 760), outline=(40, 130, 100), width=7)
    draw.text((120, 830), "图 1 生物结构示意图", fill=(30, 90, 70))
    draw.text((650, 420), "2. 化学结构式", fill=(30, 30, 40))
    draw.text((680, 520), "H3C—CH2—OH", fill=(20, 20, 30))
    draw.text((90, 1050), "3. 结合图 1 解释实验现象并写出结论。", fill=(30, 30, 40))
    output = BytesIO()
    image.save(output, format="PNG")
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")


PROMPT = server.segmentation_prompt(
    "Benchmark image containing a title, explanatory text, a biology diagram, "
    "a chemical structure, and question text. Preserve small captions."
)


def main() -> None:
    image = server.add_coordinate_grid(test_image())
    report = []
    for model in MODELS:
        started = time.perf_counter()
        parsed, error = server.qwen_request(image, PROMPT, model=model)
        elapsed = round(time.perf_counter() - started, 2)
        if isinstance(parsed, dict):
            regions = parsed.get("regions", [])
        elif isinstance(parsed, list):
            # Some compatible models return the requested JSON array directly
            # instead of wrapping it in {"regions": [...]}.
            regions = parsed
        else:
            regions = []
        complete = sum(all(key in item for key in ("x", "y", "w", "h")) for item in regions if isinstance(item, dict))
        report.append({"model": model, "seconds": elapsed, "ok": not bool(error), "error": error, "regions": len(regions), "completeCoordinates": complete})
        print(json.dumps(report[-1], ensure_ascii=False))
    print("\nSummary:")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
