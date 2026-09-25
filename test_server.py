"""Regression tests for the two Qwen structured-output contracts."""

from __future__ import annotations

import base64
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
                "x": 12.50,
                "y": 8.20,
                "w": 34.00,
                "h": 21.50,
                "confidence": 0.95,
                "group": "Q1",
                "description": "Complete reaction with catalyst labels",
                "editAction": "keep",
                "polygon": None,
                "holes": None,
            }
        ],
    }


class StructuredOutputTests(unittest.TestCase):
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
            {"id": "rect", "label": "Text Block", "kind": "text", "x": 10, "y": 10, "w": 25, "h": 20, "group": "Q1"},
            {
                "id": "poly",
                "label": "Triangle Diagram",
                "kind": "diagram",
                "x": 50,
                "y": 20,
                "w": 30,
                "h": 40,
                "group": "Q2",
                "polygon": [[50, 20], [80, 20], [65, 60]],
                "holes": [{"x": 62, "y": 30, "w": 5, "h": 5}],
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
        prompt = server.supervision_prompt(regions)
        self.assertIn("exactly two aligned images", prompt)
        self.assertNotIn("three aligned images", prompt)

    def test_initial_output_omits_confidence_and_default_keep(self) -> None:
        regions = server.normalize_regions(
            [
                {
                    "id": "r1",
                    "label": "Reaction Pathway A.",
                    "kind": "chemistry",
                    "x": 12.54,
                    "y": 8.24,
                    "w": 34.06,
                    "h": 21.55,
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

    def test_invalid_pass_is_retried_before_acceptance(self) -> None:
        invalid = {"status": "pass", "issues": [], "regions": [{"id": "bad"}]}
        responses = iter([(invalid, None), (valid_supervisor_payload(), None)])
        initial = [
            {
                "id": "r0",
                "label": "Initial Block",
                "kind": "chemistry",
                "x": 1.0,
                "y": 1.0,
                "w": 10.0,
                "h": 10.0,
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
                    "x": 12.5,
                    "y": 8.2,
                    "w": 36.0,
                    "h": 21.5,
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
                "x": 12.5,
                "y": 8.2,
                "w": 34.0,
                "h": 21.5,
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
