#!/usr/bin/env python3
"""Build the TVBian page from the repo and the latest image release.

    site/build.py [--out DIR] [--release-json FILE] [--tag TAG]

The box table in README.md is the list. A row joins boards/<id>/board.conf through its
docs/<id>/board.md link. Image links are that release's tvbian-<board>-<suite>-<date>.img.xz.
An alias, boards/<id>/alias.conf, is another box that runs a listed board's image unchanged.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn, cast

REPO = "https://github.com/sormy/tvbian"
API = "https://api.github.com/repos/sormy/tvbian/releases"
DOMAIN = "tvbian.com"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

FAMILY_NAME = {"rk35xx": "Rockchip", "meson-gxl": "Amlogic", "sunxi-h616": "Allwinner"}
COLUMNS = ("form", "hardware", "install")
SPEC = re.compile(r" (RAM|eMMC)\b")
COMPACT = (
    (re.compile(r"(?<=RAM) (LP)?DDR\d\w*"), ""),
    (re.compile(r" \([^)]*(usable|sold as)[^)]*\)"), ""),
    (re.compile(r"(?<=eMMC) (HS\d*|DDR\d+)\b"), ""),
    (re.compile(r"(?<=SD) (UHS-\w+|HS)\b"), ""),
    (re.compile(r" \(OTG\)"), ""),
)
REF_LINE = re.compile(r"^\[([^\]]+)\]:\s+(\S+)", re.M)
MD_LINK = re.compile(r"\[([^\]]*)\]\[([^\]]+)\]")
BOARD_DOC = re.compile(r"docs/([^/]+)/board\.md")
IMAGE = r"^tvbian-{board}-[a-z]+-\d{{4}}-\d{{2}}-\d{{2}}\.img\.xz$"
PHOTOS = ("image1.jpg", "image1.png", "image1.jpeg", "image1.webp")
ALT_PHOTO = re.compile(r"^image1_alt(\d+)\.(jpg|png|jpeg|webp)$")
SUPPORT = {
    "tested_by_tvbian": (
        "Tested by TVBian",
        '<path d="m6 12.5 4 4 8-9"/>',
    ),
    "tested_by_user": (
        "Tested by user",
        '<circle cx="9" cy="8" r="3.5"/><path d="M3 20c0-3.5 2.7-6 6-6s6 2.5 6 6"/><path d="m15.5 11 2 2 4-4"/>',
    ),
    "not_tested": (
        "Not tested",
        '<path d="M8.8 8.8a3.3 3.3 0 1 1 4.6 3c-.9.4-1.4 1.1-1.4 2v.6"/><path d="M12 18.5h.01"/>',
    ),
    "tested_broken": (
        "Tested: broken",
        '<path d="m7 7 10 10M17 7 7 17"/>',
    ),
}

REPORT_BODY = """Board: {board} (PCB {pcb})
Image: {image}

**Result:** works / broken

**What I checked** (strike what you did not try):
- [ ] boots from SD, USB or eMMC
- [ ] HDMI picture and audio
- [ ] Ethernet
- [ ] Wi-Fi and Bluetooth
- [ ] the remote
- [ ] video playback

**What went wrong**, if anything:

**Boot log** (serial console or `journalctl -b`):
```
paste here
```
"""
ALIAS_ICON = (
    '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/>'
    '<path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>'
)


ACTION_ICONS = {
    "Download": '<path d="M12 4v11m-5-5 5 5 5-5M5 20h14"/>',
    "Unreleased: wait for next Monday": '<circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/>',
    "Install guide": '<path d="M4 5a2 2 0 0 1 2-2h13v15H6a2 2 0 0 0-2 2Z"/><path d="M4 20a2 2 0 0 0 2 1h13v-3"/>',
    "Report a test": '<path d="M5 21V4h11l-2 4 2 4H5"/>',
    "Product page": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c5 5 5 13 0 18-5-5-5-13 0-18Z"/>',
    "Store": '<path d="M5 8h14l1 13H4L5 8Z"/><path d="M8 8V6a4 4 0 0 1 8 0v2"/>',
}


def svg(icon: str, stroke: str) -> str:
    return (
        f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="{stroke}" '
        f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{icon}</svg>'
    )


def action(label: str, url: str, kind: str) -> str:
    """An icon button, its label the tooltip; no URL renders it disabled."""
    icon = svg(ACTION_ICONS[label], "1.8")
    classes = f"act {kind}".strip()
    if url:
        return f'<a class="{classes}" href="{esc(url)}" aria-label="{esc(label)}">{icon}</a>'
    return f'<span class="{classes}" role="img" aria-disabled="true" aria-label="{esc(label)}" tabindex="0">{icon}</span>'


def badge(kind: str, label: str, icon: str) -> str:
    return (
        f'<span class="{kind}" role="img" tabindex="0" aria-label="{esc(label)}">'
        f'{svg(icon, "2.2")}</span>'
    )


@dataclass(frozen=True)
class Asset:
    name: str
    url: str


@dataclass(frozen=True)
class Release:
    tag: str
    page: str
    assets: tuple[Asset, ...]


@dataclass(frozen=True)
class Row:
    form: str
    hardware: tuple[str, ...]
    install: str
    guide: str

    @property
    def soc(self) -> str:
        return self.hardware[0].removeprefix("SoC ") if self.hardware else ""


@dataclass(frozen=True)
class Card:
    id: str
    name: str
    pcb: str
    family_id: str
    family: str
    previous: str
    row: Row | None
    photo: Path | None
    alternates: tuple[Path, ...]
    home: str = ""
    store: str = ""
    support: str = "tested_by_tvbian"
    alias_of: str = ""
    alias_of_name: str = ""


def die(message: str) -> NoReturn:
    raise SystemExit(message)


def mapping(value: object, what: str) -> dict[str, object]:
    if not isinstance(value, dict):
        die(f"{what} is not an object")
    out: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            die(f"{what} has a non-string key")
        out[key] = cast(object, item)
    return out


def text_of(value: object, what: str) -> str:
    if not isinstance(value, str) or not value:
        die(f"{what} is missing")
    return value


def parse_release(value: object) -> Release:
    obj = mapping(value, "release")
    if obj.get("prerelease") is True or obj.get("draft") is True:
        die(f"{obj.get('tag_name', 'release')} is not an image release")
    raw = obj.get("assets")
    if not isinstance(raw, list):
        die("release has no assets")
    assets: list[Asset] = []
    for item in raw:
        asset = mapping(cast(object, item), "asset")
        assets.append(
            Asset(
                text_of(asset.get("name"), "asset name"),
                text_of(asset.get("browser_download_url"), "asset url"),
            )
        )
    return Release(
        text_of(obj.get("tag_name"), "tag"),
        text_of(obj.get("html_url"), "release url"),
        tuple(assets),
    )


def github_json(url: str, timeout: int = 30) -> object:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "tvbian-site"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return cast(object, json.loads(response.read().decode()))


def fetch_release(tag: str) -> Release:
    url = f"{API}/tags/{urllib.parse.quote(tag, safe='')}" if tag else f"{API}/latest"
    return parse_release(github_json(url))


def fetch_stars() -> int | None:
    try:
        payload = github_json(API.removesuffix("/releases"), timeout=5)
        count = payload.get("stargazers_count") if isinstance(payload, dict) else None
        if type(count) is int and count >= 0:
            return count
    except (OSError, ValueError):
        pass
    print("GitHub star count unavailable; omitting badge", file=sys.stderr)
    return None


def conf_value(text: str, key: str) -> str:
    match = re.search(rf"^{key}=(.*)$", text, re.M)
    if not match:
        return ""
    value = match.group(1).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def cells(line: str) -> list[str]:
    return [part.strip() for part in line.strip().strip("|").split("|")]


Fields = dict[str, str]
ALIAS_MARK = "↳"


def box_table(
    text: str,
) -> tuple[dict[str, str], list[tuple[str, Fields]], dict[tuple[str, str], Fields]]:
    """The box table's references, its board rows, and each alias row under its board."""
    refs = {match.group(1): match.group(2) for match in REF_LINE.finditer(text)}
    lines = text.splitlines()
    header: list[str] | None = None
    rows: list[tuple[str, Fields]] = []
    aliases: dict[tuple[str, str], Fields] = {}
    for line in lines:
        if not line.startswith("|"):
            if header is not None:
                break
            continue
        fields = cells(line)
        if header is None:
            names = [
                field.strip().lower().replace("\\", "").replace("*", "")
                for field in fields
            ]
            if "board" in names and "install" in names:
                header = names
            continue
        if set(fields[0]) <= {"-", ":"}:
            continue
        named = {header[i]: fields[i] for i in range(min(len(header), len(fields)))}
        if fields[0].startswith(ALIAS_MARK):
            if not rows:
                die(f"alias row before any board: {fields[0]}")
            aliases[(rows[-1][0], fields[0].removeprefix(ALIAS_MARK).strip())] = named
            continue
        link = MD_LINK.search(fields[0])
        if link is None:
            die(f"box row has no board link: {fields[0]}")
        target = refs.get(link.group(2), "")
        found = BOARD_DOC.fullmatch(target)
        if found is None:
            die(f"{link.group(2)} does not point at docs/<board>/board.md")
        rows.append((found.group(1), named))
    if header is None:
        die("README.md has no box table")
    return refs, rows, aliases


def row_from(fields: Fields, refs: dict[str, str]) -> Row:
    missing = [column for column in COLUMNS if column not in fields]
    if missing:
        die(f"box table is missing {', '.join(missing)}")
    install = fields["install"]
    link = MD_LINK.search(install)
    guide = refs.get(link.group(2), "") if link else ""
    label = link.group(1) if link else install
    hardware = tuple(item.strip().replace("**", "") for item in fields["hardware"].split("·"))
    return Row(fields["form"], hardware, label, guide)


def board_support(text: str, board_id: str) -> str:
    level = conf_value(text, "BOARD_SUPPORT") or "tested_by_tvbian"
    if level not in SUPPORT:
        die(f"{board_id}: BOARD_SUPPORT must be one of {', '.join(SUPPORT)}")
    return level


def find_alternates(folder: Path) -> tuple[Path, ...]:
    found = [
        (int(match.group(1)), path)
        for path in (folder.iterdir() if folder.is_dir() else ())
        if (match := ALT_PHOTO.match(path.name))
    ]
    return tuple(path for _, path in sorted(found))


def find_photo(folder: Path) -> Path | None:
    for name in PHOTOS:
        photo = folder / name
        if photo.is_file():
            return photo
    return None


def load_aliases(
    root: Path, boards: dict[str, Card], rows: dict[tuple[str, str], Row]
) -> dict[str, list[Card]]:
    aliases: dict[str, list[Card]] = {}
    for conf in sorted((root / "boards").glob("*/alias.conf")):
        alias_id = conf.parent.name
        if (conf.parent / "board.conf").is_file():
            die(f"boards/{alias_id} has both board.conf and alias.conf")
        text = conf.read_text()
        parent = boards.get(conf_value(text, "BOARD_ALIAS_OF"))
        if parent is None:
            die(f"boards/{alias_id}/alias.conf: BOARD_ALIAS_OF names no listed board")
        name = conf_value(text, "BOARD_NAME")
        if not name:
            die(f"boards/{alias_id}/alias.conf names no BOARD_NAME")
        row = rows.get((parent.id, name))
        if row is None:
            die(f"README.md lists no {name} under {parent.name}")
        aliases.setdefault(parent.id, []).append(
            Card(
                alias_id,
                name,
                conf_value(text, "BOARD_PCB"),
                parent.family_id,
                parent.family,
                parent.previous,
                row,
                find_photo(root / "docs" / alias_id),
                find_alternates(root / "docs" / alias_id),
                conf_value(text, "BOARD_HOME"),
                conf_value(text, "BOARD_STORE"),
                board_support(text, alias_id),
                alias_of=parent.id,
                alias_of_name=parent.name,
            )
        )
    return aliases


def load_cards(root: Path) -> list[Card]:
    refs, rows, listed_aliases = box_table((root / "README.md").read_text())
    if not rows:
        die("README.md has no listed boards")
    by_id = {board_id: row_from(fields, refs) for board_id, fields in rows}
    if len(by_id) != len(rows):
        die("README.md lists a board more than once")
    known = {path.parent.name for path in (root / "boards").glob("*/board.conf")}
    missing = [board_id for board_id in by_id if board_id not in known]
    if missing:
        die(
            f"README names a board with no boards/<id>/board.conf: {', '.join(missing)}"
        )
    cards: list[Card] = []
    order = [board_id for board_id, _ in rows]
    for board_id in order:
        text = (root / "boards" / board_id / "board.conf").read_text()
        if conf_value(text, "BOARD_ID") != board_id:
            die(f"boards/{board_id}/board.conf BOARD_ID does not match its directory")
        family = conf_value(text, "BOARD_FAMILY")
        support = board_support(text, board_id)
        if not (root / "docs" / board_id / "board.md").is_file():
            die(f"{board_id}: missing board report")
        row = by_id[board_id]
        if not row.guide or not (root / row.guide).is_file():
            die(f"{board_id}: install link must name an existing guide")
        cards.append(
            Card(
                board_id,
                conf_value(text, "BOARD_NAME") or board_id,
                conf_value(text, "BOARD_PCB"),
                family,
                FAMILY_NAME.get(family, family),
                conf_value(text, "BOARD_RENAMED_FROM"),
                row,
                find_photo(root / "docs" / board_id),
                find_alternates(root / "docs" / board_id),
                conf_value(text, "BOARD_HOME"),
                conf_value(text, "BOARD_STORE"),
                support,
            )
        )
    alias_rows = {key: row_from(fields, refs) for key, fields in listed_aliases.items()}
    aliases = load_aliases(root, {card.id: card for card in cards}, alias_rows)
    every = cards + [alias for group in aliases.values() for alias in group]
    return sorted(every, key=lambda card: card.name.casefold())


def image_for(board_id: str, release: Release, previous: str = "") -> Asset | None:
    # a release cut before a rename still carries the old board id in the filename
    for candidate in (board_id, previous):
        if not candidate:
            continue
        pattern = re.compile(IMAGE.format(board=re.escape(candidate)))
        found = [asset for asset in release.assets if pattern.fullmatch(asset.name)]
        if found:
            if len(found) > 1:
                die(f"{board_id}: release has multiple plain images")
            return found[0]
    return None


def png_size(data: bytes) -> tuple[int, int] | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    return None


def jpeg_size(data: bytes) -> tuple[int, int] | None:
    index, end = 2, len(data)
    while index + 8 < end and data[index] == 0xFF:
        marker = data[index + 1]
        while marker == 0xFF and index + 2 < end:
            index += 1
            marker = data[index + 1]
        index += 2
        if marker in (0xD8, 0xD9):
            continue
        if index + 2 > end:
            return None
        length = int.from_bytes(data[index : index + 2], "big")
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB):
            if index + 7 > end:
                return None
            height = int.from_bytes(data[index + 3 : index + 5], "big")
            width = int.from_bytes(data[index + 5 : index + 7], "big")
            return width, height
        index += length
    return None


def image_size(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes()
    return png_size(data) or jpeg_size(data)


def esc(value: str) -> str:
    return html.escape(value, quote=True)


ALT = {
    "box": "Android TV box",
    "stick": "Android TV stick",
    "mini box": "Mini Android TV box",
}
DESCRIPTION = (
    "Linux for Android TV boxes, based on Debian. TVBian supplies kernels, drivers and board support "
    "with package updates through apt and fresh weekly images."
)


def report_url(card: Card, image: Asset | None) -> str:
    body = REPORT_BODY.format(
        board=card.id, pcb=card.pcb or "?", image=image.name if image else "?"
    )
    query = urllib.parse.urlencode({"title": f"Test report: {card.name}", "body": body})
    return f"{REPO}/issues/new?{query}"


def search_text(card: Card) -> str:
    soc = card.row.soc if card.row else ""
    return " ".join((card.name, card.pcb, card.alias_of_name, card.family, soc))


def compact(item: str) -> str:
    """A README hardware item as its card shows it, the details left to the README."""
    for pattern, replacement in COMPACT:
        item = pattern.sub(replacement, item)
    return item


def spec_line(card: Card) -> str:
    row = card.row
    if row is None:
        return ""
    bits: list[str] = []
    chip = row.soc
    if chip:
        bits.append(chip)
    bits += [compact(item) for item in row.hardware[1:] if SPEC.search(item)]
    return " · ".join(bits)


Shot = tuple[str, tuple[int, int] | None]


def card_html(card: Card, release: Release, shots: list[Shot]) -> str:
    row = card.row
    kind = ALT.get(row.form, "Android TV box") if row else "Android TV box"
    alt = esc(f"{card.name}, {kind}")
    images = []
    for index, (src, size) in enumerate(shots):
        dims = f' width="{size[0]}" height="{size[1]}"' if size else ""
        active = " active" if index == 0 else ""
        images.append(
            f'<img class="shot{active}" src="{esc(src)}" alt="{alt}"{dims} loading="lazy" decoding="async" />'
        )
    shot = "".join(images) or '<div class="shot blank">no photo</div>'
    if len(shots) > 1:
        shot += (
            '<button class="slide prev" type="button" aria-label="Previous case">‹</button>'
            '<button class="slide next" type="button" aria-label="Next case">›</button>'
        )
    items = row.hardware[1:] if row else ()
    hardware = " · ".join(compact(item) for item in items if not SPEC.search(item))
    badges = [badge("support", *SUPPORT[card.support])]
    if card.alias_of:
        badges.append(badge("alias", f"Alias of {card.alias_of_name}", ALIAS_ICON))
    badge_row = f'<div class="badges">{"".join(badges)}</div>'
    parts = [
        f'<p class="pcb"><span>PCB</span> {esc(card.pcb)}</p>' if card.pcb else "",
        f'<p class="pcb"><span>ALIAS</span> {esc(card.alias_of_name)}</p>' if card.alias_of else "",
        f'<p class="spec chip">{esc(spec_line(card))}</p>' if spec_line(card) else "",
        f'<p class="spec">{esc(hardware)}</p>' if hardware else "",
    ]
    image = image_for(card.alias_of or card.id, release, card.previous)
    guide = row.guide if row and row.install else ""
    links = (
        ("Download", image.url if image else "", "primary"),
        ("Install guide", f"{REPO}/blob/main/{guide}#install" if guide else "", ""),
        ("Report a test", report_url(card, image) if card.support == "not_tested" else "", ""),
        ("Product page", card.home, ""),
        ("Store", card.store, ""),
    )
    actions = "".join(action(label, url, kind) for label, url, kind in links if url)
    if not image:
        actions = action("Unreleased: wait for next Monday", "", "primary") + actions
    doc = f"{REPO}/blob/main/docs/{card.alias_of or card.id}/board.md"
    return (
        f'<article class="board" id="{esc(card.id)}" data-family="{esc(card.family)}" data-support="{esc(card.support)}" data-search="{esc(search_text(card))}">'
        f'<figure class="stage">{shot}{badge_row}</figure><div class="body">'
        f'<h3 class="board-title"><a href="{esc(doc)}">{esc(card.name)}</a></h3>'
        f'{"".join(parts)}<div class="actions">{actions}</div></div></article>'
    )


# what a login shows: illustrative values in base/motd's own layout
EXAMPLE_KERNELS = {"rk35xx": "6.1.172", "sunxi64": "6.18.60", "meson64": "6.18.60"}
MOTD_LABEL = 14
MOTD_CELL = 18


def motd_field(label: str, html: str, text: str, cell: int = 0) -> str:
    """A label column, then a value padded to the cell by its plain text, as the motd's printf does."""
    return f"{label:<{MOTD_LABEL}}{html}{' ' * max(cell - len(text), 0)}"


def terminal_html(root: Path, cards: list[Card], release: Release | None = None) -> str:
    if not cards:
        return ""
    card = next(card for card in cards if not card.alias_of)
    image = image_for(card.id, release, card.previous) if release else None
    suite = image.name.rsplit("-", 4)[1] if image else "trixie"
    conf = (root / "boards" / card.id / "board.conf").read_text()
    hostname = conf_value(conf, "BOARD_HOSTNAME") or card.id
    motd = (root / "base" / "motd").read_text()
    logo = motd.split("cat <<'LOGO'\n", 1)[1].split("\nLOGO", 1)[0].strip("\n")
    kernel = f"{EXAMPLE_KERNELS.get(card.family_id, '6.18.60')}-tvb-{card.family_id}"

    def green(text: str) -> str:
        return f'<span class="ansi-green">{esc(text)}</span>'

    lines = [
        f' TVBian for <strong>{esc(card.name)}</strong> <span class="dim">{esc(card.pcb)}</span>, '
        f"running Linux {green(kernel)}",
        "",
        " " + motd_field("Base:", f"Debian stable ({esc(suite)})", ""),
        " "
        + motd_field(
            "Updates:",
            f"Kernel upgrade enabled and {green('20')} packages available for upgrade",
            "",
        ),
        "",
        " "
        + motd_field(
            "IPv4:",
            '<span class="ansi-yellow">(LAN)</span> ' + green("192.168.1.42"),
            "",
        )
        + '  <span class="ansi-yellow">(WAN)</span> <span class="ansi-magenta">198.51.100.42</span>',
        " "
        + motd_field(
            "IPv6:",
            '<span class="ansi-yellow">(WAN)</span> '
            '<span class="ansi-magenta">2001:db8:4248:5000:fcfd:fcff:fe12:3456</span>',
            "",
        ),
        "",
        " "
        + motd_field("Load:", green("8%"), "8%", MOTD_CELL)
        + motd_field("Uptime:", green("4h 1m"), ""),
        " "
        + motd_field(
            "Memory:",
            green("12%") + " of 1.44G",
            "12% of 1.44G",
            MOTD_CELL,
        )
        + motd_field("CPU temp:", green("44 °C"), ""),
        " " + motd_field("Disk /:", green("32%") + " of 15G", ""),
    ]
    motd_text = "\n".join(lines)
    return (
        '<div class="terminal" aria-label="Example TVBian SSH login">'
        '<div class="terminal-bar" aria-hidden="true"><i></i><i></i><i></i>'
        f"<span>root@{esc(hostname)}:~</span></div>"
        '<div class="terminal-body">'
        f'<p class="login-command"><span class="dim">~ %</span> ssh root@{esc(hostname)}</p>'
        f'<pre class="motd-logo" aria-label="TVBian">{esc(logo)}</pre>'
        f'<pre class="motd">{motd_text}</pre>'
        f'<p class="login-prompt">root@{esc(hostname)}:~# <span class="cursor" aria-hidden="true"></span></p>'
        "</div></div>"
    )


def linked_data(cards: list[Card]) -> str:
    devices: list[dict[str, object]] = []
    for index, card in enumerate(cards, 1):
        devices.append(
            {
                "@type": "ListItem",
                "position": index,
                "name": card.name,
                "url": f"https://{DOMAIN}/#{card.id}",
            }
        )
    graph: list[dict[str, object]] = [
        {
            "@type": "WebSite",
            "name": "TVBian",
            "url": f"https://{DOMAIN}/",
            "description": DESCRIPTION,
        },
        {
            "@type": "ItemList",
            "name": "Android TV boxes TVBian supports",
            "itemListElement": devices,
        },
    ]
    return json.dumps(
        {"@context": "https://schema.org", "@graph": graph}, ensure_ascii=True
    )


def coffee_html(root: Path) -> str:
    path = root / "site" / "coffee.url"
    if not path.is_file():
        return ""
    url = path.read_text().strip()
    if not url:
        return ""
    if not url.startswith("https://"):
        die("site/coffee.url must be one https URL")
    return f'<a class="coffee" href="{esc(url)}">Buy a coffee</a>'


def write_site(
    root: Path, release: Release, out: Path, stars: int | None = None
) -> None:
    cards = load_cards(root)
    if not any(image_for(card.id, release, card.previous) for card in cards):
        die(f"{release.tag}: no image downloads for the listed boards")
    out.mkdir(parents=True, exist_ok=True)
    media = out / "media"
    if media.exists():
        shutil.rmtree(media)
    media.mkdir()
    blocks: list[str] = []
    for card in cards:
        shots: list[Shot] = []
        photos = ((card.photo,) if card.photo else ()) + card.alternates
        for index, photo in enumerate(photos):
            src = f"media/{card.id}{f'-{index}' if index else ''}{photo.suffix}"
            shutil.copyfile(photo, out / src)
            shots.append((src, image_size(photo)))
        blocks.append(card_html(card, release, shots))
    page = (HERE / "template.html").read_text()
    replacements = {
        "@@STARS@@": (
            f'<span class="github-stars" aria-label="{stars:,} {"star" if stars == 1 else "stars"}"><span aria-hidden="true">★</span> {stars:,}</span>'
            if stars is not None
            else ""
        ),
        "@@DESCRIPTION@@": esc(DESCRIPTION),
        "@@JSONLD@@": linked_data(cards),
        "@@TAG@@": esc(release.tag),
        "@@RELEASE_URL@@": esc(release.page),
        "@@REPO@@": REPO,
        "@@BOARDS@@": "\n".join(blocks),
        "@@FILTERS@@": "\n".join(
            f'<button class="filter" data-filter="{esc(family)}" aria-pressed="false">{esc(family)}</button>'
            for family in dict.fromkeys(card.family for card in cards)
        ),
        "@@COFFEE@@": coffee_html(root),
        "@@TERMINAL@@": terminal_html(root, cards, release),
    }
    for token, value in replacements.items():
        if token not in page:
            die(f"template is missing {token}")
        page = page.replace(token, value)
    if "@@" in page:
        die("template has an unfilled token")
    (out / "index.html").write_text(page)
    (out / "CNAME").write_text(DOMAIN + "\n")
    print(f"✓ {out / 'index.html'} ({release.tag}, {len(cards)} boards)")


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Build the TVBian page.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--release-json", type=Path)
    parser.add_argument("--tag", default="")
    args = parser.parse_args(argv)
    if args.release_json:
        release = parse_release(cast(object, json.loads(args.release_json.read_text())))
    else:
        release = fetch_release(args.tag)
    stars = fetch_stars() if not args.release_json else None
    write_site(
        args.root, release, args.out or args.root / "build" / "out" / "site", stars
    )


if __name__ == "__main__":
    main(sys.argv[1:])
