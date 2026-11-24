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


def mode(
    width: int, height: int, refresh: float = 60.0, current: bool = False
) -> dict[str, object]:
    return {"width": width, "height": height, "refresh": refresh, "current": current}


def head(width_mm: int, height_mm: int, modes: list[dict[str, object]]) -> dict[str, object]:
    return {
        "name": "HDMI-A-1",
        "enabled": True,
        "physical_size": {"width": width_mm, "height": height_mm},
        "modes": modes,
    }


class FittingModeTest(unittest.TestCase):
    CASES = [
        # (what, panel in mm, modes, the mode chosen)
        (
            "a 3:2 panel whose scaler prefers 16:9: the 16:10 mode, the closest",
            (290, 190),
            [mode(2048, 1152, current=True), mode(1920, 1200, 59.95), mode(1600, 1200)],
            (1920, 1200),
        ),
        (
            "a 16:9 TV in its 16:9 mode: kept",
            (1210, 680),
            [mode(1920, 1080, current=True), mode(1280, 1024)],
            (1920, 1080),
        ),
        (
            "an EDID with no size: kept",
            (0, 0),
            [mode(1920, 1080, current=True), mode(1280, 1024)],
            (1920, 1080),
        ),
        (
            "two modes of the panel's shape: the larger, at its faster rate",
            (300, 225),
            [
                mode(1920, 1080, current=True),
                mode(1024, 768),
                mode(1600, 1200, 50.0),
                mode(1600, 1200, 60.0),
            ],
            (1600, 1200, 60.0),
        ),
    ]

    def test_fitting_mode(self) -> None:
        for what, (width_mm, height_mm), modes, expected in self.CASES:
            with self.subTest(what):
                chosen = SCALE_OUTPUTS.fitting_mode(head(width_mm, height_mm, modes))
                self.assertEqual(
                    (chosen["width"], chosen["height"], chosen["refresh"])[: len(expected)],
                    expected,
                )


class OutputsTest(unittest.TestCase):
    def test_enabled_outputs_scaled_at_their_fitting_mode(self) -> None:
        letterboxed = head(290, 190, [mode(2048, 1152, current=True), mode(1920, 1200)])
        off = {
            **head(0, 0, [mode(720, 576, current=True)]),
            "name": "Composite-1",
            "enabled": False,
        }
        # an output enabled before its mode is set, as one is at a compositor's start
        unset = {**head(300, 190, [mode(1920, 1080)]), "name": "HDMI-A-2"}
        outputs = SCALE_OUTPUTS.enabled_outputs([letterboxed, off, unset])
        self.assertEqual(
            [(output, (fitted["width"], fitted["height"])) for output, fitted in outputs],
            [(SCALE_OUTPUTS.Output("HDMI-A-1", 1920, 290), (1920, 1200))],
        )


if __name__ == "__main__":
    unittest.main()
