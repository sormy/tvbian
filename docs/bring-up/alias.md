# Alias bring-up

Another box that runs a listed board's image unchanged: another brand, case or PCB name on the same
hardware. It gets a card, a README row and a release line, but no image, tree or package of its own.
Anything it needs that the listed board's image lacks makes it a board.

## Do

1. **The match, from photos**: its PCB, both sides, against the listed board's: the silkscreen, the
   SoC, RAM, eMMC and Wi-Fi module. A different PCB name with the same parts can still be an alias;
   its silkscreen is recorded as it reads.
2. **Its data**: `boards/<id>/alias.conf` with `BOARD_ALIAS_OF`, the listed board; `BOARD_NAME`, the
   name it is sold under; `BOARD_PCB`, its silkscreen; `BOARD_HOME` and `BOARD_STORE` where it has a
   listing. Its photos in `docs/<id>/`, the box first as `image1.*`.
3. **The listed board's docs**: an "Also sold as" row in its `board.md` Identity, ✅ where this box
   booted the image here, else ❓; a dated worklog entry; the box under its board's row in
   `README.md`, a `↳ <name>` row of its own, every column filled, and its family's README.
4. **Its own boot**, where the box is to hand: the image from an SD card or USB stick, then the
   listed board's smoke checks: network, Wi-Fi, HDMI, the remote.

## Bites

- **The case label can lie**: the Leffot H313's says "H96 Max H313", an Allwinner model's name, over
  an RK3518. The board's chips and layout decide; its silkscreen can be relabelled too.
- **A reporter stays private**: a name or address someone reports a box under never reaches the
  repo.

## Check

- [ ] **A1** Its silkscreen and parts recorded against the listed board's
- [ ] **A2** `alias.conf` and its photos; `./build.sh test` passes
- [ ] **A3** The listed board's `board.md`, its worklog and the READMEs name it
- [ ] **A4** 👤 Optional: it boots the image here, the listed board's smoke checks pass
