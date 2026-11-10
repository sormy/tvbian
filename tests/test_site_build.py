"""site/build.py against this repo and a release held in memory. No network."""

from __future__ import annotations

import html
import json
import re
import shutil
import sys
import tempfile
import unittest
import urllib.parse
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "site"))
import build  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CARDS = build.load_cards(ROOT)
BOARDS = tuple(card.id for card in CARDS if not card.alias_of)


def asset(name: str) -> dict[str, str]:
    return {"name": name, "browser_download_url": f"https://example.test/{name}"}


def release_json(names: list[str], prerelease: bool = False) -> object:
    return {
        "tag_name": "2026-11-02",
        "html_url": "https://example.test/rel",
        "prerelease": prerelease,
        "draft": False,
        "assets": [asset(name) for name in names],
    }


def image_name(board: str, extra: str = "") -> str:
    middle = f"-{extra}" if extra else ""
    return f"tvbian-{board}-trixie{middle}-2026-11-02.img.xz"


class Parse(unittest.TestCase):
    def test_box_table_joins_board_conf(self) -> None:
        cards = build.load_cards(ROOT)
        self.assertEqual(len(cards), len({card.id for card in cards}))
        tanix = next(card for card in cards if card.id == "tanix-tx1-v2")
        self.assertEqual(tanix.name, "Tanix TX1")
        self.assertEqual(tanix.family, "Allwinner")
        assert tanix.row is not None
        self.assertEqual(tanix.row.guide, "README_ALLWINNER.md")
        self.assertEqual(tanix.row.install, "OTG")
        rockchip = next(card for card in cards if card.id == "r69-1").row
        assert rockchip is not None
        self.assertEqual(rockchip.install, "SD or OTG")
        self.assertEqual(rockchip.guide, "README_ROCKCHIP.md")
        self.assertTrue(all(card.support in build.SUPPORT for card in cards))

    def test_image_name_is_the_plain_image(self) -> None:
        names = [
            image_name("h96max-3518"),
            image_name("h96max-3518d"),
            image_name("h96max-3518", "kodi"),
            "SHA256SUMS",
        ]
        release = build.parse_release(release_json(names))
        plain = build.image_for("h96max-3518", release)
        assert plain is not None
        self.assertEqual(plain.name, image_name("h96max-3518"))
        sibling = build.image_for("h96max-3518d", release)
        assert sibling is not None
        self.assertEqual(sibling.name, image_name("h96max-3518d"))
        renamed = build.parse_release(
            release_json([image_name("r69"), image_name("r69-1")])
        )
        current = build.image_for("r69-1", renamed, "r69")
        assert current is not None
        self.assertEqual(current.name, image_name("r69-1"))
        old = build.image_for(
            "r69-1", build.parse_release(release_json([image_name("r69")])), "r69"
        )
        assert old is not None
        self.assertEqual(old.name, image_name("r69"))

    def test_prerelease_is_refused(self) -> None:
        with self.assertRaises(SystemExit):
            build.parse_release(release_json([image_name("r69-1")], prerelease=True))

    def test_photo_size(self) -> None:
        jpg = build.image_size(ROOT / "docs" / "r69-1" / "image1.jpg")
        png = build.image_size(ROOT / "docs" / "h96max-3518d" / "image1.png")
        assert jpg is not None and png is not None
        self.assertGreater(jpg[0], 0)
        self.assertGreater(png[1], 0)

    def test_terminal_follows_first_board_and_repo_logo(self) -> None:
        cards = build.load_cards(ROOT)
        banner = build.terminal_html(ROOT, cards)
        first = next(card for card in cards if not card.alias_of)
        self.assertIn(f"ssh root@{first.id}", banner)
        self.assertIn(first.pcb, banner)
        logo = (
            (ROOT / "base/motd")
            .read_text()
            .split("cat <<'LOGO'\n", 1)[1]
            .split("\nLOGO", 1)[0]
            .strip("\n")
        )
        self.assertIn(build.esc(logo), banner)
        tanix = next(card for card in cards if card.id == "tanix-tx1-v2")
        reordered = build.terminal_html(ROOT, [tanix, *cards])
        self.assertIn("ssh root@tanix-tx1", reordered)
        self.assertNotIn("ssh root@r69-1", reordered)

    def test_stars_accepts_zero_and_rejects_invalid_counts(self) -> None:
        for count, expected in (
            (7, 7),
            (0, 0),
            (-1, None),
            (True, None),
            ("7", None),
            (None, None),
        ):
            with self.subTest(count=count), patch(
                "build.urllib.request.urlopen"
            ) as request:
                request.return_value.__enter__.return_value.read.return_value = (
                    json.dumps({"stargazers_count": count}).encode()
                )
                self.assertEqual(build.fetch_stars(), expected)

    def test_stars_api_failure_is_optional(self) -> None:
        with patch("build.urllib.request.urlopen", side_effect=OSError("offline")):
            self.assertIsNone(build.fetch_stars())

    def test_card_escapes(self) -> None:
        card = build.Card("x", "<b>", "pcb", "rk35xx", "Rockchip", "", None, None, ())
        release = build.parse_release(release_json([]))
        html = build.card_html(card, release, [])
        self.assertIn("&lt;b&gt;", html)
        self.assertNotIn("<b>", html)


class Write(unittest.TestCase):
    def test_page_links_images_and_guides(self) -> None:
        names = [image_name(board) for board in BOARDS]
        release = build.parse_release(release_json(names))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            build.write_site(ROOT, release, out)
            page = (out / "index.html").read_text()
            self.assertEqual((out / "CNAME").read_text(), "tvbian.com\n")
            self.assertNotIn("@@", page)
            self.assertIn("2026-11-02", page)
            self.assertIn("https://tvbian.com/", page)
            self.assertIn('alt="R69-1, Android TV box"', page)
            self.assertIn("Android TV boxes TVBian supports", page)
            for card in CARDS:
                if card.alias_of:
                    continue
                photo = card.photo
                self.assertIsNotNone(photo)
                assert photo is not None
                self.assertTrue((out / "media" / f"{card.id}{photo.suffix}").is_file())
            r69 = article(page, "R69-1")
            self.assertIn(image_name("r69-1"), r69)
            self.assertIn("README_ROCKCHIP.md#install", r69)
            self.assertIn('aria-label="Install guide"', r69)
            stick = article(page, "H96 Max 3518D")
            self.assertNotIn("SD card", stick)
            self.assertIn("README_AMLOGIC.md#install", article(page, "H96 Max M20"))
            self.assertIn("README_ALLWINNER.md#install", article(page, "Tanix TX1"))
            self.assertIn('aria-label="Tested by TVBian"', page)
            self.assertIn('data-support="tested_by_tvbian"', page)

    def test_coffee_button(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "site").mkdir()
            (root / "site" / "coffee.url").write_text("https://example.test/coffee\n")
            self.assertIn("https://example.test/coffee", build.coffee_html(root))
            (root / "site" / "coffee.url").write_text("javascript:alert(1)\n")
            with self.assertRaises(SystemExit):
                build.coffee_html(root)


class Discovery(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "README.md").write_text(
            "| Board | Form | Hardware | Install |\n"
            "| --- | --- | --- | --- |\n"
            "| [New board][new] | stick | SoC TEST9000 · 4 GB RAM · 32 GB eMMC · RADIO9 · HDMI · USB | [OTG][guide] |\n"
            "\n[new]: docs/new-box/board.md\n[guide]: README_NEW.md\n"
        )
        board = self.root / "boards/new-box"
        board.mkdir(parents=True)
        (board / "board.conf").write_text(
            'BOARD_ID=new-box\nBOARD_NAME="Brand New"\nBOARD_PCB=PCB_NEW\n'
            "BOARD_FAMILY=new-family\nBOARD_HOSTNAME=new-host\n"
            "BOARD_STORE=https://example.test/store\nBOARD_HOME=https://example.test/product\n"
        )
        (self.root / "README_NEW.md").write_text("# Installation\n")
        docs = self.root / "docs/new-box"
        docs.mkdir(parents=True)
        (docs / "board.md").write_text("# New board\n")
        shutil.copyfile(ROOT / "docs/r69-1/image1.jpg", docs / "image1.jpg")
        (self.root / "base").mkdir()
        shutil.copyfile(ROOT / "base/motd", self.root / "base/motd")
        self.release = build.parse_release(release_json([image_name("new-box")]))

    def test_new_board_discovers_specs_photo_links_family_and_download(self) -> None:
        out = self.root / "output"
        build.write_site(self.root, self.release, out, stars=7)
        page = (out / "index.html").read_text()
        for expected in (
            'id="new-box"',
            'data-filter="new-family"',
            "TEST9000",
            "4 GB RAM",
            "32 GB eMMC",
            "RADIO9",
            "HDMI · USB",
            "PCB_NEW",
            "README_NEW.md#install",
            "https://example.test/store",
            "https://example.test/product",
            image_name("new-box"),
            "root@new-host",
            'class="github-stars"',
        ):
            self.assertIn(expected, page)
        self.assertEqual(page.count('id="new-box"'), 1)
        self.assertTrue((out / "media/new-box.jpg").is_file())
        self.assertIn("Debian stable (trixie)", page)
        self.assertNotIn("@@", page)

    def page(self, name: str) -> str:
        out = self.root / name
        build.write_site(self.root, self.release, out)
        return (out / "index.html").read_text()

    def alias(
        self, conf: str, alias_id: str = "new-alias", listed: str = "", emmc: str = "32 GB"
    ) -> Path:
        if listed:
            readme = self.root / "README.md"
            board = "| [New board][new] | stick | SoC TEST9000 · 4 GB RAM · 32 GB eMMC · RADIO9 · HDMI · USB | [OTG][guide] |\n"
            row = f"| ↳ {listed} | stick | SoC TEST9000 · 4 GB RAM · {emmc} eMMC · RADIO9 · HDMI · USB | [OTG][guide] |\n"
            readme.write_text(readme.read_text().replace(board, board + row))
        folder = self.root / "boards" / alias_id
        folder.mkdir()
        (folder / "alias.conf").write_text(conf)
        return folder

    def test_alias_follows_its_board_with_its_own_photo_and_the_boards_image(self) -> None:
        self.alias(
            'BOARD_ALIAS_OF=new-box\nBOARD_NAME="Other Name"\nBOARD_PCB=PCB_OTHER\n'
            "BOARD_STORE=https://example.test/other-store\n",
            listed="Other Name",
            emmc="8 GB",
        )
        photos = self.root / "docs/new-alias"
        photos.mkdir()
        shutil.copyfile(ROOT / "docs/r69-1/image1.jpg", photos / "image1.jpg")
        self.assertEqual(
            [card.id for card in build.load_cards(self.root)], ["new-box", "new-alias"]
        )
        out = self.root / "aliased"
        build.write_site(self.root, self.release, out)
        page = (out / "index.html").read_text()
        alias = page[page.index('id="new-alias"') :]
        for expected in (
            "Other Name",
            "PCB_OTHER",
            "<span>ALIAS</span> Brand New",
            "TEST9000 · 4 GB RAM · 8 GB eMMC",
            'class="alias" role="img" tabindex="0" aria-label="Alias of Brand New"',
            "https://example.test/other-store",
            image_name("new-box"),
            "docs/new-box/board.md",
            'data-family="new-family"',
        ):
            self.assertIn(expected, alias)
        self.assertTrue((out / "media/new-alias.jpg").is_file())

    def test_cards_sort_by_name_and_the_terminal_shows_a_board(self) -> None:
        self.alias('BOARD_ALIAS_OF=new-box\nBOARD_NAME="aardvark box"\n', listed="aardvark box")
        cards = build.load_cards(self.root)
        self.assertEqual([card.id for card in cards], ["new-alias", "new-box"])
        self.assertIn("new-host", build.terminal_html(self.root, cards))

    def test_alias_errors(self) -> None:
        for conf, error in (
            ('BOARD_ALIAS_OF=missing\nBOARD_NAME="X"\n', "names no listed board"),
            ("BOARD_ALIAS_OF=new-box\n", "names no BOARD_NAME"),
            ('BOARD_ALIAS_OF=new-box\nBOARD_NAME="Unlisted"\n', "lists no Unlisted under Brand New"),
        ):
            folder = self.alias(conf, "bad-alias")
            with self.assertRaisesRegex(SystemExit, error):
                build.load_cards(self.root)
            shutil.rmtree(folder)
        both = self.alias('BOARD_ALIAS_OF=new-box\nBOARD_NAME="X"\n', "new-box2")
        (both / "board.conf").write_text("BOARD_ID=new-box2\n")
        with self.assertRaisesRegex(SystemExit, "both board.conf and alias.conf"):
            build.load_cards(self.root)

    def test_release_suffix_keeps_the_original_image_date(self) -> None:
        data = release_json([image_name("new-box")])
        assert isinstance(data, dict)
        data["tag_name"] = "2026-11-02.2"
        release = build.parse_release(data)
        out = self.root / "second-release"
        build.write_site(self.root, release, out)
        page = (out / "index.html").read_text()
        self.assertIn("2026-11-02.2", page)
        self.assertIn(image_name("new-box"), page)
        self.assertNotIn("2026-11-02.2.img.xz", page)

    def test_terminal_codename_comes_from_the_selected_image(self) -> None:
        release = build.parse_release(
            release_json(
                [
                    image_name("new-box").replace("trixie", "bookworm"),
                ]
            )
        )
        banner = build.terminal_html(self.root, build.load_cards(self.root), release)
        self.assertIn("Debian stable (bookworm)", banner)
        self.assertNotIn("trixie", banner)

    def test_old_release_uses_board_rename_without_site_changes(self) -> None:
        conf = self.root / "boards/new-box/board.conf"
        conf.write_text(conf.read_text() + "BOARD_RENAMED_FROM=old-box\n")
        release = build.parse_release(release_json([image_name("old-box")]))
        out = self.root / "renamed"
        build.write_site(self.root, release, out)
        page = (out / "index.html").read_text()
        self.assertIn('id="new-box"', page)
        self.assertIn(image_name("old-box"), page)

    def test_alternate_photos_slide_in_number_order(self) -> None:
        photos = self.root / "docs/new-box"
        photos.mkdir(parents=True, exist_ok=True)
        for name in ("image1_alt10.jpg", "image1_alt2.jpg", "image1_alt1.jpg", "image1_altx.jpg"):
            shutil.copyfile(ROOT / "docs/r69-1/image1.jpg", photos / name)
        card = build.load_cards(self.root)[0]
        self.assertEqual(
            [path.name for path in card.alternates],
            ["image1_alt1.jpg", "image1_alt2.jpg", "image1_alt10.jpg"],
        )
        one = build.card_html(card, self.release, [("media/a.jpg", None)])
        self.assertNotIn('class="slide', one)
        two = build.card_html(card, self.release, [("media/a.jpg", None), ("media/b.jpg", None)])
        self.assertEqual(two.count('class="shot'), 2)
        self.assertEqual(two.count('class="shot active"'), 1)
        self.assertIn('class="slide next"', two)

    def test_untested_board_says_so(self) -> None:
        conf = self.root / "boards/new-box/board.conf"
        conf.write_text(conf.read_text() + "BOARD_SUPPORT=not_tested\n")
        card = build.load_cards(self.root)[0]
        html = build.card_html(card, self.release, [])
        self.assertIn('data-support="not_tested"', html)
        self.assertIn('aria-label="Not tested"', html)

    def test_a_board_missing_from_the_release_is_unreleased(self) -> None:
        card = build.load_cards(self.root)[0]
        empty = build.parse_release(release_json([]))
        self.assertIn('aria-label="Download"', build.card_html(card, self.release, []))
        unreleased = build.card_html(card, empty, [])
        self.assertIn('aria-disabled="true" aria-label="Unreleased: wait for next Monday"', unreleased)
        self.assertNotIn('aria-label="Download"', unreleased)

    def test_only_a_not_tested_card_asks_for_a_report(self) -> None:
        conf = self.root / "boards/new-box/board.conf"
        self.assertNotIn('aria-label="Report a test"', self.page("tested"))
        conf.write_text(conf.read_text() + "BOARD_SUPPORT=not_tested\n")
        page = self.page("not-tested")
        link = re.search(r'href="([^"]+)" aria-label="Report a test"', page)
        assert link
        query = urllib.parse.parse_qs(urllib.parse.urlparse(html.unescape(link[1])).query)
        self.assertEqual(query["title"], ["Test report: Brand New"])
        self.assertIn("Board: new-box (PCB PCB_NEW)", query["body"][0])
        self.assertIn(f"Image: {image_name('new-box')}", query["body"][0])

    def test_support_refuses_an_unknown_level(self) -> None:
        conf = self.root / "boards/new-box/board.conf"
        conf.write_text(conf.read_text() + "BOARD_SUPPORT=maybe\n")
        with self.assertRaisesRegex(SystemExit, "BOARD_SUPPORT"):
            build.load_cards(self.root)

    def test_unlisted_board_is_not_advertised(self) -> None:
        board = self.root / "boards/work-in-progress"
        board.mkdir()
        (board / "board.conf").write_text("BOARD_ID=work-in-progress\n")
        self.assertEqual([card.id for card in build.load_cards(self.root)], ["new-box"])

    def test_duplicate_board_and_missing_guide_are_errors(self) -> None:
        readme = self.root / "README.md"
        original = readme.read_text()
        row = original.splitlines()[2]
        readme.write_text(original.replace(row, row + "\n" + row))
        with self.assertRaisesRegex(SystemExit, "more than once"):
            build.load_cards(self.root)
        readme.write_text(original)
        (self.root / "README_NEW.md").unlink()
        with self.assertRaisesRegex(SystemExit, "existing guide"):
            build.load_cards(self.root)

    def test_release_without_downloads_does_not_write_a_site(self) -> None:
        out = self.root / "output"
        release = build.parse_release(release_json(["SHA256SUMS"]))
        with self.assertRaisesRegex(SystemExit, "no image downloads"):
            build.write_site(self.root, release, out)
        self.assertFalse(out.exists())

    def test_ambiguous_images_are_rejected(self) -> None:
        release = build.parse_release(
            release_json(
                [
                    image_name("new-box"),
                    image_name("new-box").replace("trixie", "bookworm"),
                ]
            )
        )
        with self.assertRaisesRegex(SystemExit, "multiple plain images"):
            build.image_for("new-box", release)

    def test_offline_cli_does_not_need_github(self) -> None:
        payload = self.root / "release.json"
        payload.write_text(json.dumps(release_json([image_name("new-box")])))
        with patch(
            "build.urllib.request.urlopen",
            side_effect=AssertionError("offline build requested GitHub"),
        ):
            build.main(
                [
                    "--root",
                    str(self.root),
                    "--release-json",
                    str(payload),
                    "--out",
                    str(self.root / "offline"),
                ]
            )
        self.assertIn("Brand New", (self.root / "offline/index.html").read_text())

    def test_github_token_is_sent_as_header(self) -> None:
        with patch.dict(build.os.environ, {"GH_TOKEN": "test-only-token"}), patch(
            "build.urllib.request.urlopen"
        ) as request:
            request.return_value.__enter__.return_value.read.return_value = (
                b'{"stargazers_count": 7}'
            )
            self.assertEqual(build.fetch_stars(), 7)
            self.assertEqual(
                request.call_args.args[0].get_header("Authorization"),
                "Bearer test-only-token",
            )


def article(page: str, name: str) -> str:
    start = page.index(f">{build.esc(name)}</a>")
    return page[start : page.index("</article>", start)]


class Json(unittest.TestCase):
    def test_round_trip_types(self) -> None:
        release = build.parse_release(
            json.loads(json.dumps(release_json([image_name("r69-1")])))
        )
        self.assertEqual(release.tag, "2026-11-02")
        self.assertEqual(release.assets[0].name, image_name("r69-1"))


if __name__ == "__main__":
    unittest.main()


class Compact(unittest.TestCase):
    def test_a_readme_item_compacts_to_its_card_form(self) -> None:
        for item, card in (
            ("2 GB RAM LPDDR3 (1.5 GB usable)", "2 GB RAM"),
            ("4 GB RAM DDR3", "4 GB RAM"),
            ("16 GB eMMC HS200", "16 GB eMMC"),
            ("16 GB eMMC DDR52", "16 GB eMMC"),
            ("1.5 GB RAM LPDDR3 (sold as 2 GB)", "1.5 GB RAM"),
            ("SD HS", "SD"),
            ("4 GB RAM (on a spare rank)", "4 GB RAM (on a spare rank)"),
            ("SD UHS-I", "SD"),
            ("no SD", "no SD"),
            ("USB-A 3.0 (OTG) + USB-A 2.0", "USB-A 3.0 + USB-A 2.0"),
            ("USB-C 2.0 (OTG) + USB-A 2.0", "USB-C 2.0 + USB-A 2.0"),
            ("LAN 100M", "LAN 100M"),
        ):
            with self.subTest(item=item):
                self.assertEqual(build.compact(item), card)
