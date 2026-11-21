"""bases/<source>.translate.conf: a vendor dialect's vocabulary, each token's outcome in mainline's.

The format is in README.md, "The translation".
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field

from dtcx import HERE

DROPPED, UNRESOLVED, MAINLINE, UNSUPPORTED = ("none", "unresolved", "mainline", "unsupported")
# a vendor node mainline does not have, around the nodes it does: its children stand in its place
WRAPPER = "wrapper"
# a property dropped from mainline's node as well as the vendor's
WITHHOLD = "withhold"
# what a rule can do with a property, beside dropping it or asking
CONVERSIONS = (
    "same",
    "as",
    "flag",
    "scale",
    "bits",
    "alias",
    "pinctrl",
    "gpio",
    "opp-v2",
    "opp-range",
    "bank-1v8",
    "implies",
    "supply-name",
    "used-as",
)
# what a rule leaves out or leaves open, which a comment above it must explain
NEEDS_COMMENT = (
    DROPPED,
    UNRESOLVED,
    UNSUPPORTED,
    WITHHOLD,
    "none-if-empty",
    "unused-by",
    "supply-name",
)
ACTIONS = (
    DROPPED,
    UNRESOLVED,
    MAINLINE,
    UNSUPPORTED,
    WRAPPER,
    WITHHOLD,
    "none-if-empty",
    "unused-by",
    *CONVERSIONS,
)
# vendor nodes written as the mainline nodes they describe, each by its conversion in conversions.py
BUILT = (
    "pwrseq",
    "vbus",
    "enable",
    "boot-voltage",
    "leds",
    "hdmi-connector",
    "bluetooth-reset",
    "bluetooth-uart",
    "bank-bias",
    "recovery-key",
    "supply",
    "aml-slot",
    "aml-pwrseq",
    "aml-32k",
    "cec",
    "rk-sound-card",
    "pwm-ir",
    "init-voltage",
    "hdmi-ddc-i2c",
    "console",
    "led-roles",
    "adc-recovery",
    "shared-reset",
    "radio-pcm",
    "gpu-power",
)


class Pattern:
    """A vendor token with {n} for an instance number, {w} for a word, * for any text."""

    def __init__(self, text: str) -> None:
        escaped = re.escape(text).replace(r"\{n\}", r"(\d+)").replace(r"\{w\}", r"([a-z]+)")
        self.regex = re.compile(f"^{escaped.replace(r'\*', '.*')}$")

    def match(self, token: str) -> list[str] | None:
        found = self.regex.match(token)
        return list(found.groups()) if found else None


def fill(template: str, captures: list[str]) -> str:
    """The template with each {n} or {w} replaced by the next capture, in order."""
    for capture in captures:
        template = re.sub(r"\{[nw]\}", capture, template, count=1)
    return template


@dataclass
class Rule:
    """One vendor token's outcome: an action and its arguments."""

    pattern: Pattern
    action: str
    args: list[str] = field(default_factory=list)
    scope: str = ""  # a vendor compatible or node name it applies within; empty for any
    text: str = ""  # the pattern as written, for the report


@dataclass
class Vocabulary:
    compatibles: dict[str, list[str]] = field(default_factory=dict)
    names: list[Rule] = field(default_factory=list)
    labels: list[Rule] = field(default_factory=list)
    values: list[Rule] = field(default_factory=list)  # args: the property, the mainline value
    nodes: list[Rule] = field(default_factory=list)
    props: list[Rule] = field(default_factory=list)
    clocks: list[Rule] = field(default_factory=list)
    states: list[Rule] = field(default_factory=list)  # pin states other than default
    also: list[Rule] = field(default_factory=list)  # conversions run beside a node's translation
    cells: dict[str, tuple[int, int]] = field(default_factory=dict)
    soc: str = ""
    pin_group: str = ""  # the property that makes a vendor node a pin group
    pin_functions: list[str] = field(default_factory=list)  # mainline pinctrl driver sources
    soc_patches: str = ""

    @staticmethod
    def load(base: str) -> Vocabulary:
        path = HERE / "bases" / f"{base}.translate.conf"
        if not path.is_file():
            sys.exit(f"no translation onto {base}: {path} does not exist")
        return Vocabulary.parse(path.read_text(), str(path))

    @staticmethod
    def parse(text: str, where: str = "translation") -> Vocabulary:
        out = Vocabulary()
        explained = False  # a comment block explains the rules below it, up to a blank line
        for number, raw in enumerate(text.splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("##"):
                explained = False
                continue
            if line.startswith("#"):  # a property's own # always follows a keyword
                explained = True
                continue
            key, *words = line.split()
            if key == "compatible":
                out.compatibles[words[0]] = words[1:]
            elif key in ("name", "label"):
                token, _, scope = words[0].partition("@")
                getattr(out, f"{key}s").append(Rule(Pattern(token), "as", words[1:2], scope, token))
            elif key == "value":
                out.values.append(Rule(Pattern(words[1]), "as", [words[0], words[2]]))
            elif key == "also":
                out.also.append(Rule(Pattern(words[0]), words[1], words[2:], "", words[0]))
            elif key in ("node", "prop", "clock", "state"):
                at = next((i for i, w in enumerate(words) if w in ACTIONS + BUILT), None)
                if at is None:
                    sys.exit(f"{where}:{number}: no action")
                action, args = words[at], words[at + 1 :]
                if action in NEEDS_COMMENT and not explained:
                    sys.exit(f"{where}:{number}: {words[0]}: {action} with no comment above it")
                for word in words[:at]:  # a node's name has its own @, the unit address
                    token, _, scope = (word, "", "") if key == "node" else word.partition("@")
                    getattr(out, f"{key}s").append(Rule(Pattern(token), action, args, scope, token))
            elif key == "cells":
                out.cells[words[0]] = (int(words[1]), int(words[2]))
            elif key == "pin-functions":
                out.pin_functions += words
            elif key == "pin-group":
                out.pin_group = words[0]
            elif key == "soc":
                out.soc = words[0]
            elif key == "soc-patches":
                out.soc_patches = words[0]
            else:
                sys.exit(f"{where}:{number}: unknown key {key}")
        return out
