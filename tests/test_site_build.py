"""site/build.py against this repo and a release held in memory. No network."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
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

    def test_readme_names_every_alias(self) -> None:
        readme = (ROOT / "README.md").read_text()
        for card in CARDS:
            if card.alias_of:
                self.assertIn(card.name, readme)

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
        self.assertIn("ssh root@r69-1", banner)
        self.assertIn("XR821_V1.1", banner)
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
        card = build.Card("x", "<b>", "pcb", "rk35xx", "Rockchip", "", None, None)
        release = build.parse_release(release_json([]))
        html = build.card_html(card, release, None, None)
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
            self.assertIn(">Install</a>", r69)
            stick = article(page, "H96 Max 3518D")
            self.assertNotIn("SD card", stick)
            self.assertIn("README_AMLOGIC.md#install", article(page, "H96 Max M20"))
            self.assertIn("README_ALLWINNER.md#install", article(page, "Tanix TX1"))

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
            "| Box | Form | SoC | RAM | eMMC | Wi-Fi/BT | Ports | Install |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
            "| [New board][new] | stick | TEST9000 | 4G | 32G | RADIO9 | HDMI, USB | [OTG][guide] |\n"
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

    def alias(self, conf: str, alias_id: str = "new-alias") -> Path:
        folder = self.root / "boards" / alias_id
        folder.mkdir()
        (folder / "alias.conf").write_text(conf)
        return folder

    def test_alias_follows_its_board_with_its_own_photo_and_the_boards_image(self) -> None:
        self.alias(
            'BOARD_ALIAS_OF=new-box\nBOARD_NAME="Other Name"\nBOARD_PCB=PCB_OTHER\n'
            "BOARD_STORE=https://example.test/other-store\n"
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
            "https://example.test/other-store",
            image_name("new-box"),
            "docs/new-box/board.md",
            'data-family="new-family"',
        ):
            self.assertIn(expected, alias)
        self.assertTrue((out / "media/new-alias.jpg").is_file())

    def test_alias_errors(self) -> None:
        for conf, error in (
            ('BOARD_ALIAS_OF=missing\nBOARD_NAME="X"\n', "names no listed board"),
            ("BOARD_ALIAS_OF=new-box\n", "names no BOARD_NAME"),
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
