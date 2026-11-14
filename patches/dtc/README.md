# dtc: patches to round-trip a vendor DTB

Vanilla `dtc` v1.8.1 plus six patches, built by `./build.sh tool dtc` into `build/bin/dtc`. Plain
dtc decompiles references as raw numbers; the patched one prints labels:

```
dtc  :  clocks = <0x02 0xaf>;
dtc  :  clocks = <&cru 0xaf>;          # -P
```

```sh
./build.sh tool dtc          # fetch, patch, build, then run the gate
./build.sh tool dtc --test   # rerun the gate on boards/*/board.dtb
```

| Flag | Does                                                                 |
| ---- | -------------------------------------------------------------------- |
| `-P` | print phandles as `&label` (`&{/path}` when the blob has no symbols) |
| `-n` | drop the generated `__symbols__` node; `-@` rebuilds it identically  |
| `-s` | also sort each node's labels, so `-P -s` output is stable            |

## How it works

The blob has what is needed: `__symbols__` gives the label names, and each target's
`#<specifier>-cells` gives the argument count. The patch marks references in a fixed list of
properties (`clocks`, `*-gpios`, `pinctrl-N`, `*-supply`, `resets`, `power-domains`,
`rockchip,pins` and others), and dtc's writer prints the marks as labels.

A property is marked only if its whole value decodes; otherwise (`interrupt-map`, a target without
its `#*-cells`) it stays numeric. The list must be declared, because a value alone cannot tell a
phandle from a number like `bus-width = <4>`. Every name in it is also in
`tools/dtcx/references.py`; `tests/test_tools_dtcx_references.py` fails if they disagree, so add a
new name to both.

Mistakes in the list are silent either way:

- A missing name leaves a reference as a number that is only right for the blob it came from.
  `snps,mtl-rx-config` did this and pointed at the PHY after a rebuild.
- An extra name turns a number into a reference. `rockchip,taskqueue-node = <2>` is a queue index,
  not a phandle, and printed as `&cru`.

A round trip catches neither, so check a new name against the vendor dtsi.

## The guarantee

Explicit `phandle = <N>;` properties are kept, so the output recompiles byte-identical, with or
without `__symbols__`. `make test` enforces it. The factory trees keep these lines; a board's
`board.dts` drops them, proven equal except for numbering by `tools/dtcx/canonical.py`.

Never ship a sorted (`-s`) tree: sorting reorders the blob. It is only for comparing trees.

## Upstream

None of this is in dtc (checked against master, 2026-08): `add_phandle_marker()` exists but is used
only for overlay `__local_fixups__`, which board DTBs do not have. Each patch is formatted to send.
0003 is a standalone round-trip bug fix: `add_label()` prepends, so a blob decompiled and recompiled
with `-@` gets its labels in reverse order.
