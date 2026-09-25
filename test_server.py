"""Regression tests for the two Qwen structured-output contracts."""

from __future__ import annotations

import unittest
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
        with patch("server.qwen_request", side_effect=lambda *args, **kwargs: next(responses)):
            regions, audit, passed = server.supervise_regions("data:image/png;base64,AA==", initial)
        self.assertTrue(passed)
        self.assertEqual([item["status"] for item in audit], ["revise", "pass"])
        self.assertEqual(regions[0]["kind"], "chemical")


if __name__ == "__main__":
    unittest.main()
