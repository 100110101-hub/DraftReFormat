"""Regression tests for the two Qwen structured-output contracts."""

from __future__ import annotations

import base64
import json
import threading
import urllib.request
import unittest
from io import BytesIO
from unittest.mock import patch

import server


def valid_supervisor_payload() -> dict:
    return {
        "status": "pass",
        "issues": [],
        "regions": [
            {
                "id": "r1",
                "label": "Reaction Pathway A",
                "kind": "chemical",
                "polygon": [[12.50, 8.20], [46.50, 8.20], [42.00, 29.70], [15.00, 29.70]],
                "confidence": 0.95,
                "group": "Q1",
                "description": "Complete reaction with catalyst labels",
                "editAction": "keep",
                "holes": None,
            }
        ],
    }


class StructuredOutputTests(unittest.TestCase):
    def test_reanalysis_endpoint_sends_boundary_overlay_and_accepts_corrected_polygon(self) -> None:
        current = [[40, 40], [60, 40], [60, 60], [40, 60]]
        corrected = [[41, 41], [58, 40], [59, 57], [43, 59]]
        captured: dict = {}

        def fake_request(images, prompt, *args, **kwargs):
            captured["images"] = images
            captured["prompt"] = prompt
            return {"polygon": corrected}, None

        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            request = urllib.request.Request(
                f"http://127.0.0.1:{httpd.server_port}/api/reanalyze-region",
                data=json.dumps({"image": "data:image/png;base64,eA==", "polygon": current, "kind": "chemistry", "label": "Reaction", "description": "Reaction with arrows", "holes": [{"polygon": [[45, 45], [50, 45], [50, 50]]}]}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with (
                patch("server.make_region_reanalysis_images", return_value=(["source-with-polygon", "coordinate-overlay"], True)),
                patch("server.qwen_request", side_effect=fake_request),
            ):
                with urllib.request.urlopen(request, timeout=5) as response:
                    result = json.loads(response.read().decode())
            self.assertEqual(result["polygon"], corrected)
            self.assertEqual(captured["images"], ["source-with-polygon", "coordinate-overlay"])
            self.assertIn("ONLY the one selected semantic region", captured["prompt"])
            self.assertIn("not a request to split", captured["prompt"])
            self.assertIn("reaction arrow", captured["prompt"])
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_reanalysis_accepts_same_or_smaller_valid_polygons(self) -> None:
        current = [[40, 40], [60, 40], [60, 60], [40, 60]]
        corrected = [[41, 41], [59, 41], [59, 59], [41, 59]]
        self.assertEqual(server.validate_reanalyzed_polygon(current), [])
        self.assertEqual(server.validate_reanalyzed_polygon(corrected), [])
        self.assertTrue(server.validate_reanalyzed_polygon([[40, 40], [60, 60], [40, 60], [60, 40]]))

    def test_reanalysis_prompt_shows_current_polygon_and_preserves_chemistry_arrows(self) -> None:
        prompt = server.region_reanalysis_prompt({"polygon": [[10, 10], [20, 10], [20, 20]], "kind": "chemistry"})
        self.assertIn("Independently reanalyze ONLY", prompt)
        self.assertIn("CURRENT REGION TO REANALYZE", prompt)
        self.assertIn("arrowhead", prompt)
        self.assertIn('"polygon"', prompt)

    def test_reanalysis_falls_back_to_original_image_without_pillow(self) -> None:
        image = "data:image/png;base64,eA=="
        with patch.object(server, "Image", None):
            images, has_overlay = server.make_region_reanalysis_images(image, {"polygon": [[1, 1], [2, 1], [2, 2]]})
        self.assertEqual(images, [image])
        self.assertFalse(has_overlay)
        prompt = server.region_reanalysis_prompt({"polygon": [[1, 1], [2, 1], [2, 2]]}, has_boundary_overlay=has_overlay)
        self.assertIn("No image overlay could be rendered", prompt)
        self.assertIn("exact current polygon coordinates", prompt)

    def test_all_chemistry_agents_require_complete_edges_and_safety_clearance(self) -> None:
        initial = server.segmentation_prompt()
        revision = server.segmentation_revision_prompt([], ["Expand clipped atom label"], [])
        supervisor = server.supervision_prompt([])

        for prompt in (initial, revision, supervisor):
            self.assertIn("1.5%", prompt)
            self.assertIn("arrowhead", prompt.lower())
            self.assertTrue("safety" in prompt.lower() or "clearance" in prompt.lower())

        self.assertIn("stereochemical wedges/dashes", initial)
        self.assertIn("mark revise and expand", supervisor)
        self.assertIn("expand clipped/tight chemistry boundaries", revision.lower())

    def test_qwen_request_serializes_history_before_current_two_images(self) -> None:
        captured: dict = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"choices":[{"message":{"content":"{\\"regions\\":[]}"}}]}'

        def fake_urlopen(request, timeout):
            captured["payload"] = __import__("json").loads(request.data.decode("utf-8"))
            return FakeResponse()

        history = [
            {"role": "user", "content": "initial prompt"},
            {"role": "assistant", "content": '{"regions":[{"id":"r1"}]}'},
        ]
        with (
            patch.dict(server.os.environ, {"DASHSCOPE_API_KEY": "test-key"}),
            patch("server.urllib.request.urlopen", side_effect=fake_urlopen),
        ):
            parsed, error = server.qwen_request(["overlay-1", "overlay-2"], "revision prompt", history=history)

        self.assertIsNone(error)
        self.assertEqual(parsed, {"regions": []})
        messages = captured["payload"]["messages"]
        self.assertEqual(messages[:2], history)
        self.assertEqual(messages[2]["role"], "user")
        self.assertEqual([part["image_url"]["url"] for part in messages[2]["content"][:2]], ["overlay-1", "overlay-2"])
        self.assertEqual(messages[2]["content"][2], {"type": "text", "text": "revision prompt"})

    @unittest.skipIf(server.Image is None, "Pillow is required")
    def test_supervision_uses_two_boundary_overlay_images(self) -> None:
        source = server.Image.new("RGB", (400, 300), "white")
        encoded = BytesIO()
        source.save(encoded, format="PNG")
        image_data_url = "data:image/png;base64," + base64.b64encode(encoded.getvalue()).decode("ascii")
        regions = [
            {"id": "rect", "label": "Text Block", "kind": "text", "x": 10, "y": 10, "w": 25, "h": 20, "polygon": [[10, 10], [35, 10], [33, 28], [12, 30]], "group": "Q1"},
            {
                "id": "poly",
                "label": "Triangle Diagram",
                "kind": "diagram",
                "x": 50, "y": 20, "w": 30, "h": 40,
                "group": "Q2",
                "polygon": [[50, 20], [80, 20], [65, 60]],
                "holes": [{"polygon": [[62, 30], [67, 30], [65, 35]]}],
            },
        ]
        images = server.make_supervision_images(image_data_url, regions)
        self.assertEqual(len(images), 2)
        rendered = [server.Image.open(BytesIO(base64.b64decode(item.split(",", 1)[1]))).convert("RGB") for item in images]
        self.assertEqual(rendered[0].size, source.size)
        self.assertGreater(rendered[1].width, rendered[0].width)
        self.assertGreater(rendered[1].height, rendered[0].height)
        self.assertNotEqual(rendered[0].getpixel((40, 30)), (255, 255, 255))
        self.assertNotEqual(rendered[0].getpixel((200, 60)), (255, 255, 255))
        self.assertNotEqual(rendered[0].getpixel((252, 90)), (255, 255, 255))
        self.assertEqual(rendered[0].getpixel((200, 180)), (255, 255, 255))
        prompt = server.supervision_prompt(regions)
        self.assertIn("exactly two aligned images", prompt)
        self.assertNotIn("three aligned images", prompt)
        self.assertNotIn('"x":', prompt)
        revision = server.segmentation_revision_prompt(regions, ["adjust edge"], regions)
        self.assertNotIn('"x":', revision)
        self.assertIn('"holes": [', revision)
        self.assertIn('"polygon":', revision)

    def test_initial_output_omits_confidence_and_default_keep(self) -> None:
        regions = server.normalize_regions(
            [
                {
                    "id": "r1",
                    "label": "Reaction Pathway A.",
                    "kind": "chemistry",
                    "polygon": [[12.54, 8.24], [46.60, 8.24], [46.60, 29.79], [12.54, 29.79]],
                    "confidence": 0.91,
                    "group": "Q1",
                    "editAction": "keep",
                    "unknown": "discard me",
                }
            ],
            precision=1,
            include_confidence=False,
            include_keep_action=False,
        )
        self.assertEqual(
            regions,
            [
                {
                    "id": "r1",
                    "label": "Reaction Pathway A",
                    "kind": "chemistry",
                    "x": 12.5,
                    "y": 8.2,
                    "w": 34.1,
                    "h": 21.6,
                    "group": "Q1",
                    "polygon": [[12.5, 8.2], [46.6, 8.2], [46.6, 29.8], [12.5, 29.8]],
                }
            ],
        )

    def test_supervisor_schema_and_enum_are_preserved(self) -> None:
        payload = valid_supervisor_payload()
        self.assertEqual(server.validate_supervision_response(payload), [])
        regions = server.normalize_regions(payload["regions"], precision=2)
        self.assertEqual(regions[0]["kind"], "chemical")
        self.assertEqual(regions[0]["editAction"], "keep")
        self.assertEqual(regions[0]["confidence"], 0.95)
        self.assertEqual(regions[0]["polygon"], payload["regions"][0]["polygon"])

    def test_supervisor_schema_rejects_rectangles_without_polygons(self) -> None:
        payload = valid_supervisor_payload()
        region = payload["regions"][0]
        region.pop("polygon")
        region.update({"x": 12.5, "y": 8.2, "w": 34.0, "h": 21.5})
        violations = server.validate_supervision_response(payload)
        self.assertTrue(any("extra fields" in item for item in violations))
        self.assertTrue(any("polygon" in item for item in violations))

    def test_supervisor_holes_accept_only_polygon_geometry(self) -> None:
        payload = valid_supervisor_payload()
        payload["regions"][0]["holes"] = [{"polygon": [[20, 15], [25, 14], [29, 18], [23, 21]]}]
        self.assertEqual(server.validate_supervision_response(payload), [])
        payload["regions"][0]["holes"] = [{"x": 20, "y": 15, "w": 8, "h": 6}]
        self.assertTrue(any("holes" in item for item in server.validate_supervision_response(payload)))

    def test_invalid_pass_is_retried_before_acceptance(self) -> None:
        invalid = {"status": "pass", "issues": [], "regions": [{"id": "bad"}]}
        responses = iter([(invalid, None), (valid_supervisor_payload(), None)])
        initial = [
            {
                "id": "r0",
                "label": "Initial Block",
                    "kind": "chemistry",
                    "polygon": [[1.0, 1.0], [11.0, 1.0], [11.0, 11.0], [1.0, 11.0]],
                "group": "Q1",
            }
        ]
        sent_images: list[list[str]] = []

        def fake_request(images: list[str], *args, **kwargs):
            sent_images.append(images)
            return next(responses)

        with (
            patch("server.make_supervision_images", return_value=["overlay-1", "overlay-2"]),
            patch("server.qwen_request", side_effect=fake_request),
        ):
            regions, audit, passed = server.supervise_regions("source-image", initial)
        self.assertTrue(passed)
        self.assertEqual([item["status"] for item in audit], ["revise", "pass"])
        self.assertEqual(regions[0]["kind"], "chemical")
        self.assertEqual(sent_images, [["overlay-1", "overlay-2"], ["overlay-1", "overlay-2"]])

    def test_supervision_round_override_cannot_exceed_ten(self) -> None:
        revise = valid_supervisor_payload()
        revise["status"] = "revise"
        revise["issues"] = ["Tighten polygon boundary"]
        initial = [{
            "id": "r0", "label": "Initial Block", "kind": "chemistry", "group": "Q1",
            "polygon": [[1, 1], [11, 1], [11, 11], [1, 11]],
        }]
        with (
            patch.dict(server.os.environ, {"QWEN_SUPERVISOR_ROUNDS": "99"}),
            patch("server.make_supervision_images", return_value=["overlay-1", "overlay-2"]),
            patch("server.qwen_request", return_value=(revise, None)),
            patch("server.revise_regions", return_value=(initial, None)),
        ):
            _, audit, passed = server.supervise_regions("source-image", initial)
        self.assertFalse(passed)
        self.assertEqual(len(audit), 10)

    def test_splitter_contract_requires_polygons_for_regions_and_holes(self) -> None:
        valid = {
            "regions": [{
                "id": "r1", "label": "Text", "kind": "text", "group": "Q1",
                "polygon": [[10, 10], [40, 12], [35, 30], [12, 28]],
                "holes": [{"polygon": [[20, 15], [24, 16], [22, 20]]}],
            }]
        }
        self.assertEqual(server.validate_segmentation_response(valid), [])
        boxed = {"regions": [{**valid["regions"][0], "polygon": None, "x": 10, "y": 10, "w": 30, "h": 20, "holes": [{"x": 20, "y": 15, "w": 4, "h": 5}]}]}
        violations = server.validate_segmentation_response(boxed)
        self.assertTrue(any("forbidden or extra" in item for item in violations))
        self.assertTrue(any("polygon" in item for item in violations))
        self.assertTrue(any("holes" in item for item in violations))

    def test_region_normalizer_does_not_reconstruct_model_rectangles(self) -> None:
        boxed = [{"id": "r1", "label": "Text", "kind": "text", "x": 10, "y": 10, "w": 30, "h": 20, "group": "Q1"}]
        self.assertEqual(server.normalize_regions(boxed), [])

    def test_model_visible_region_payload_strips_editor_bounds_and_rectangular_holes(self) -> None:
        internal = [{
            "id": "r1", "label": "Text", "kind": "text", "x": 10, "y": 10, "w": 30, "h": 20,
            "polygon": [[10, 10], [40, 12], [38, 30], [12, 28]], "group": "Q1",
            "holes": [{"polygon": [[20, 15], [24, 16], [22, 20]]}],
        }]
        visible = server.model_visible_regions(internal)
        self.assertEqual(set(visible[0]), {"id", "label", "kind", "polygon", "group", "holes"})
        self.assertEqual(set(visible[0]["holes"][0]), {"polygon"})
        self.assertNotIn('"x":', __import__("json").dumps(visible))

    def test_splitter_revision_uses_two_overlays_and_conversation_history(self) -> None:
        first_review = valid_supervisor_payload()
        first_review["status"] = "revise"
        first_review["issues"] = ["Expand the right edge"]
        final_review = valid_supervisor_payload()
        splitter_revision = {
            "regions": [
                {
                    "id": "r1",
                    "label": "Reaction Pathway A",
                    "kind": "chemistry",
                    "polygon": [[12.5, 8.2], [48.5, 8.2], [48.5, 29.7], [12.5, 29.7]],
                    "group": "Q1",
                    "description": "Expanded complete reaction",
                }
            ]
        }
        supervisor_responses = iter([(first_review, None), (final_review, None)])
        initial = [
            {
                "id": "r1",
                "label": "Reaction Pathway A",
                "kind": "chemistry",
                "polygon": [[12.5, 8.2], [46.5, 8.2], [46.5, 29.7], [12.5, 29.7]],
                "group": "Q1",
            }
        ]
        initial_history = [
            {"role": "user", "content": "initial segmentation prompt"},
            {"role": "assistant", "content": '{"regions":[]}'},
        ]
        calls: list[dict] = []

        def fake_request(images, prompt, *args, **kwargs):
            history = kwargs.get("history")
            calls.append({"images": images, "prompt": prompt, "history": [dict(item) for item in history] if history else history})
            if "Continue your role as the document-layout" in prompt:
                return splitter_revision, None
            return next(supervisor_responses)

        with (
            patch("server.make_supervision_images", return_value=["overlay-1", "overlay-2"]),
            patch("server.qwen_request", side_effect=fake_request),
        ):
            regions, audit, passed = server.supervise_regions("source-image", initial, initial_history)

        self.assertTrue(passed)
        self.assertEqual([item["status"] for item in audit], ["revise", "pass"])
        self.assertEqual(regions[0]["kind"], "chemical")
        self.assertEqual(len(calls), 3)
        revision_call = calls[1]
        self.assertEqual(revision_call["images"], ["overlay-1", "overlay-2"])
        self.assertEqual(revision_call["history"], initial_history)
        self.assertIn("exactly two aligned images", revision_call["prompt"])
        self.assertIn("No separate clean original image", revision_call["prompt"])
        self.assertIn("Expand the right edge", revision_call["prompt"])


if __name__ == "__main__":
    unittest.main()
