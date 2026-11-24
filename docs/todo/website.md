# tvbian.com

What the page still lacks.

- [ ] **The page follows `README.md`**: the README holds every word the page says, the system and
      contact sections and the ways to help included, and `site/build.py` renders them by heading;
      the template keeps the design alone.
- [ ] **Sponsored**: commercial bring-up and store links to buy a supported box. Empty at first,
      with an email to ask; the maintainer vets each by hand. ❓ the address, one at `tvbian.com`.
- [ ] **Donate**: pays for AI time and the maintainer's, through a trusted platform: GitHub Sponsors
      beside the repo, or Open Collective. ❓ which; `site/coffee.url` takes its link.
- [ ] **Board photos resized at build time**; they ship as committed.
- [ ] **A user's report links its issue**: a `tested_by_user` or `tested_broken` board names the
      issue a user reported it in.
- [ ] **Board variants**: boxes sold as one model that look identical outside but differ inside (a
      different Wi-Fi chip, a different device tree), told apart by the version suffix on the PCB
      silkscreen. `BOARD_VARIANT_OF=<board>` beside `BOARD_ALIAS_OF`: an alias runs its board's
      image unchanged; a variant has its own image (tree, wireless), and the site shows it with its
      siblings under the one model, with how to tell which you have (the silkscreen suffix), not as
      an unrelated board.
- [ ] **A board's PCB year on its card, and a filter by year** beside the existing filters: the year
      the board was made, from its silkscreen's date or its release, so a reader can tell an older
      revision from a newer one at a glance.
