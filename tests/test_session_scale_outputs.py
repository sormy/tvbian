"""session/desktop/scale-outputs: each screen's scale from its EDID size and current mode."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import unittest
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[1] / "session/desktop/scale-outputs"


def load() -> ModuleType:
    loader = importlib.machinery.SourceFileLoader("scale_outputs", str(SCRIPT))
    spec = importlib.util.spec_from_loader("scale_outputs", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


SCALE_OUTPUTS = load()


class ScaleTest(unittest.TestCase):
    CASES = [
        # (what, width in pixels, width in mm, scale)
        ("a 13.5-inch 2256x1504 laptop panel, 198 ppi", 2256, 290, 1.5),
        ("a 1080p TV, 55 inches", 1920, 1210, 1.0),
        ("an EDID with no size", 3840, 0, 1.0),
        ("a 27-inch 4K monitor, 163 ppi", 3840, 597, 1.25),
        ("a 13.6-inch 2560x1664 panel, 224 ppi", 2560, 290, 1.75),
        ("a 24-inch 1080p monitor, 92 ppi", 1920, 531, 1.0),
        ("just past a quarter step, 144 ppi", 2268, 400, 1.25),
        ("a 6-inch 4K panel, past 2", 3840, 140, 5.5),
    ]

    def test_scale(self) -> None:
        for what, width_px, width_mm, expected in self.CASES:
            with self.subTest(what):
                output = SCALE_OUTPUTS.Output("HDMI-A-1", width_px, width_mm)
                self.assertEqual(output.scale(), expected)


class OutputsTest(unittest.TestCase):
    def test_enabled_outputs_at_their_current_mode(self) -> None:
        heads = [
            {
                "name": "HDMI-A-1",
                "enabled": True,
                "physical_size": {"width": 290},
                "modes": [
                    {"width": 1920, "current": False},
                    {"width": 2256, "current": True},
                ],
            },
            {
                "name": "Composite-1",
                "enabled": False,
                "physical_size": {"width": 0},
                "modes": [{"width": 720, "current": True}],
            },
        ]
        outputs = SCALE_OUTPUTS.enabled_outputs(heads)
        self.assertEqual(outputs, [SCALE_OUTPUTS.Output("HDMI-A-1", 2256, 290)])


if __name__ == "__main__":
    unittest.main()
