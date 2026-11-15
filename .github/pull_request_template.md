Thanks for bringing a box up! A few questions help us review it quickly. The rules behind them are
in `docs/bring-up/finish.md`.

## What does this PR bring?

- [ ] A new board
- [ ] A new family (kernel, U-Boot, tools)
- [ ] Only a family's tools (backup, restore, loader)
- [ ] A driver: …
- [ ] A fix or a change

Does it need another PR, or does another PR need it? Link it here: …

## How did you bring it up?

- How did you get a console: serial, USB OTG, or over the network?
- Where did the device tree come from: the box's stock dump, its stock image, or elsewhere (link
  please)?
- Did you do anything by hand that the docs don't describe? …

## Photos

Please add these to `docs/<board>/`, cropped, sharp and under 200 KB each, and attach the
full-resolution originals to this PR:

- [ ] `image1`: the box with its remote
- [ ] `image1_alt1`, `image1_alt2`…: the same box in another colour, if sold so (another name is
      an alias, `docs/bring-up/alias.md`)
- [ ] `image2`: the ports
- [ ] `image3`: everything in the package, retail box too
- [ ] `pcb-top`, `pcb-bottom`, with the heat sink off
- [ ] `pcb-<chip>` for any other chip, close enough to read its markings
- [ ] The serial pads marked TX, RX and GND, if you used them

## What else could this change affect?

A fix for one board can break others, so tell us what it touches:

- [ ] Only this board's files
- [ ] A kernel patch
- [ ] A family's U-Boot
- [ ] An extra: FFmpeg, VA-API, Mesa, other: …
- [ ] A driver other boards use

Which families does it reach, and where did you run it on each? …

## Regression run

Which profile, on which boxes? …

<details><summary>report.md</summary>

…

</details>

## Stock image (optional, but very welcome)

If you can, dump the stock firmware, compress it (`xz` works well) and share a link from any file
host, so we can keep it on record: …

## How did it go?

- Which AI model and effort did you use? …
- Was anything in `docs/bring-up/` unclear, missing or wrong? …
- Are you happy with how the bring-up went, and with the result?
- Is there anything that still doesn't work the way you need?
