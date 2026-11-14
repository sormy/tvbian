# dtcx: decompile a device tree blob into readable source

`dtc` decompiles a blob into raw numbers: `<&cru 0x101>`, `<0x00 0x58 0x04>`, `<0x1b7740>`. The
vendor's source used names from the dt-bindings headers instead. `dtcx` puts those names back:
`<&cru CLK_SARADC>`, `<GIC_SPI 88 IRQ_TYPE_LEVEL_HIGH>`, `<1800000>`.

Named values make a tree portable between binding versions: switching vendor to mainline means
changing the `#include`s and the few names that differ.

Run on the host after `./build.sh tool dtc`. The first run of a base fetches its headers.

```sh
tools/dtcx/dtcx.py -n <base> factory_board.dtb > factory_board.dts   # kernel tree, no __symbols__
tools/dtcx/dtcx.py --strict <base> factory_uboot.dtb > factory_uboot.dts
tools/dtcx/dtcx.py --render <base> board.dts > board.dts.new           # re-render a tree, unproven
tools/dtcx/dtcx.py --include <base>                                    # the base's include root
tools/dtcx/translate.py <source> <target> factory_board.dts > factory_board_translated.dts
tools/dtcx/semdiff.py <old.dtb> <new.dtb>                              # what changed, by meaning
tools/dtcx/canonical.py [--base <base>] <a.dtb> <b.dtb>               # equal except phandle numbers
tools/dtcx/upstream.py --prove board.dtb <source> <target> board.dts   # the tree as a board file
tools/dtcx/bindings.py <kernel tree> kernel/<kernel>.conf <out dir>    # bindings with our patches
```

## Proofs

- **dtcx** writes a tree only if it compiles back to the same blob: compiled with the base's headers
  and decompiled again, it must match the original decompile exactly. `--strict` also fails when a
  provider cell has no single name.
- **canonical.py** proves two blobs equal except for phandle numbers. It reads the blobs directly
  (every node, disabled ones too, every property, the memory reservations) and replaces each proven
  phandle with its target's path. Anything else that differs is reported. A value it cannot decode
  is compared as raw bytes; if it holds a number that is a phandle pointing at different nodes in
  the two trees, that is reported too, unless the property is declared numeric.
- **references.py** is the one list of which properties hold phandles and how to decode them. dtc's
  own `-P` table must agree with it (`tests/test_tools_dtcx_references.py` checks).

## Bases

A base is `bases/<kind>-<soc>-<vendor|mainline>-<version>.conf`, for example
`kernel-rk3528-vendor-6.1` or `uboot-rk3528-mainline-2026.10`. Each board names two per tree in
`board.conf`: `_SOURCE`, the one its factory blob was built from, and `_TARGET`, the one its final
tree compiles against.

| Key       | Meaning                                                                                  |
| --------- | ---------------------------------------------------------------------------------------- |
| `source`  | repository, commit and include directory, written into the tree                          |
| `url`     | where to fetch the headers from, once, into `build/dtcx/<name>/`                         |
| `header`  | one dt-bindings header                                                                   |
| `local`   | a header no public tree has, kept in `tools/dtcx/headers/`                               |
| `render`  | the renderers to run                                                                     |
| `cells`   | `<provider> <properties> <prefixes>`: name the cell after a reference; a `.h` limits it  |
| `decimal` | vendor quantities to print in decimal; `<node>:<property>` when a name is ambiguous      |
| `gpio`    | vendor properties holding GPIO specifiers                                                |
| `ref`     | vendor properties holding bare phandles                                                 |
| `numbers` | properties holding plain numbers, never phandles; printed as read                        |
| `mask`    | `<property> <pattern>`: print a bitmask as the OR of its one-bit names                   |
| `rules`   | inherit another base's `decimal`, `gpio` and `ref`, except `ref`s a binding defines      |

| Renderer        | Writes                                                              |
| --------------- | ------------------------------------------------------------------- |
| `cells`         | provider cells: clocks, resets, SCMI, power domains                 |
| `gic`           | `GIC_SPI`/`GIC_PPI`, `IRQ_TYPE_…`, the CPU mask, under the GIC only |
| `gpio-flags`    | `GPIO_ACTIVE_HIGH`, `GPIO_ACTIVE_LOW`, `GPIO_OPEN_DRAIN`            |
| `rockchip-pins` | `<bank RK_PB4 func &conf>`, `RK_FUNC_GPIO`, `<&gpio4 RK_PC3 …>`     |
| `meson-gpio`    | Amlogic pin names: `GPIODV_24`, `GPIOAO_2`                          |
| `input-codes`   | `KEY_…`, `BTN_…`, including `rockchip,key_table` key codes          |
| `thermal`       | `THERMAL_NO_LIMIT`                                                  |
| `opp-hz`        | `/bits/ 64 <1200000000>`                                            |

Always on, for every base:

- Decimal for unit suffixes (`-hz`, `-microvolt`, `-us`, …), `#*-cells`, `clock-frequency`, the
  standard names in `DECIMAL`, and the arguments after each decoded reference. Not for `opp-hz`.
- Values dtc misread as strings become cells again: `"", "\f5"` is `<800000>`.
- Aliases use the target's label when it has one.
- Tables of fixed-size entries (`TABLE_ENTRY`: key tables, voltage selectors) print one `<…>` per
  entry, packed to the line width.
- `interrupt-map` prints one `<…>` per mapping, the parent by label.

## Translation

When a board's `_SOURCE` base has a `<source>.translate.conf`, `translate.py` rewrites the factory
tree in the `_TARGET` dialect first (`factory_board_translated.dts`). The board's patch then holds
only the board's own decisions.

Each vendor node is matched to a node in mainline's SoC dtsi (fetched from the conf's `soc` URL,
with the `soc-patches` kernel conf's patches applied). Matching tries, in order: the label (only if
the address agrees), the unit address or name under the matched parent, a unique CPU address, a
unique name. A node whose compatible says it is another block never matches. Several vendor nodes
at one address become one node. SoC facts come from mainline, board facts from the factory tree.
Translation never deletes mainline content and never fixes vendor content; fixes go in the patch.
`reg` is converted to mainline's cell counts, and `"vendor, name"` reads as `vendor,name`.

The conf maps every vendor token to one outcome. Syntax:

- One rule per line: a key, then its words.
- `#` starts a comment that explains the rules below it, up to the next blank line. `##` is a
  heading.
- A rule that drops a token or leaves it open (`none`, `none-if-empty`, `unused-by`,
  `supply-name`, `unsupported`, `unresolved`) needs a comment saying why.
- In patterns, `{n}` is an instance number, `{w}` a word, `*` any text. `token@scope` limits a rule
  to nodes with that vendor compatible or name (not on `node` lines).
- The first matching rule wins; scoped rules first.

| Key             | Meaning                                                                         |
| --------------- | ------------------------------------------------------------------------------- |
| `soc`           | URL of mainline's SoC dtsi, pinned to a tag                                     |
| `soc-patches`   | the kernel conf whose patches to that dtsi we apply                             |
| `cells`         | `<vendor node> <address cells> <size cells>`: mainline's counts under that node |
| `pin-group`     | the property that makes a node a pin group; unselected groups are dropped       |
| `pin-functions` | a mainline pinctrl driver source; a function it lacks is `unknown`              |
| `compatible`    | `<vendor> <mainline …>`                                                         |
| `label`         | `<vendor> <mainline>`, applied to every reference                               |
| `name`          | `<vendor> <mainline>`, for a node with no counterpart                           |
| `value`         | `<property> <vendor> <mainline>`: a quoted word in that property                |
| `node`          | `<tokens…> <action> [args]`: a vendor node by compatible, name or full name     |
| `prop`          | `<tokens…> <action> [args]`: a vendor property                                  |
| `state`         | `<tokens…> <action>`: a non-default pin state: `same`, `as <state>` or `none`   |
| `clock`         | `<tokens…> as <provider> <cell>`: a vendor clock reference, for a built node    |
| `also`          | `<token> <conversion> [args]`: a conversion besides the node's translation      |

| Action          | Does                                                                         |
| --------------- | ---------------------------------------------------------------------------- |
| `same`          | keep as written                                                              |
| `mainline`      | mainline's dtsi has it; keep only on a node without a mainline counterpart   |
| `as`            | `<name>`: rename; quoted words go through `value`                            |
| `flag`          | `<n>:<flag> …`: a number as a flag, `-` for none; other numbers are a question |
| `scale`         | `<name> <step> <offset> [<n>:-]`: write `n × step + offset`; `<n>:-` is unset |
| `bits`          | `<from>:<to> …`: map each vendor bit; any other bit is a question            |
| `gpio`          | `<high\|low> [pull]`: a sunxi GPIO as `<&pio bank pin flags>`                |
| `pinctrl`       | `pinctrl-names` with its `pinctrl-N`: keep default, others via `state`       |
| `alias`         | an `/aliases` path as the label of its translated node                       |
| `opp-v2`        | `<label>`: `operating-points` as an OPP v2 table                             |
| `opp-range`     | a supply: bound its regulator by the node's OPPs                             |
| `bank-1v8`      | a 1.8 V host: supply its pins' bank from the 1.8 V rail                      |
| `implies`       | `<name> <value>`: the vendor property means this mainline one                |
| `none`          | drop it (the comment says why that is safe)                                  |
| `none-if-empty` | `[same]`: drop when empty; keep a value with `same`, else a question         |
| `unused-by`     | `<flag>`, on a node: drop when the vendor flag is absent or 0, else a question |
| `supply-name`   | a supply by regulator name: drop when no vendor regulator has it             |
| `unresolved`    | a question for the board's bring-up                                          |
| `unsupported`   | no mainline binding exists: listed, not written                              |

`node` can also name a conversion from `conversions.py`, which builds the mainline node from the
vendor's own description: `pwrseq [parent]`, `vbus`, `enable <label>`, `boot-voltage`, `leds`,
`hdmi-connector <controller> <port>`, `bluetooth-reset <property>` with `bluetooth-uart`,
`bank-bias`, `recovery-key <level>`, and for Amlogic `aml-slot <host>`, `aml-pwrseq <host>`,
`aml-32k`. OPP rows sharing a frequency merge into one row with `opp-microvolt-speed<bin>` per speed
bin. Pin states without pin groups are not written.

`--report <file>` lists what the conf left open, one decision per line: `unresolved` (a question),
`dormant` (a question on a node the vendor disabled), `unsupported`, and `unknown` (a token the conf
does not name; never guessed). A conf is done when nothing is unknown and every drop has a reason.

## Comparing trees: semdiff.py

`semdiff.py` compares two trees by meaning, even when their layouts differ. Nodes are paired by the
CPU address of their registers (the most alike node wins when several share one address), then by
path, unique compatible, or name. Each node pairs with at most one other.

It reports blocks enabled in only one tree, and properties an enabled block drops, adds or changes,
including those of its compatible-less children (LEDs, endpoints, thermal maps, aliases). Named
lists like `clocks` with `clock-names` compare by name. A node paired by path whose registers moved
to another address is reported.

- A phandle compares as the node it points at, so renumbering is not a difference and a reference
  to another node is. Only properties `references.py` decodes, plus the base's `gpio` and `ref`
  names; anything else compares as numbers.
- An alias compares as the node its path names.
- A pin group compares only if an enabled device selects it, and so do the pin configurations it
  names.
- Not compared: disabled blocks, layout (`reg` beyond the address, `ranges`, `#…-cells`), phandle
  numbers, and node or property order. Use `canonical.py` for trees with the same layout.

## The upstream view: upstream.py

`upstream.py` writes a board's final tree the way mainline writes a board file: include the base,
then write only what the board changes, using the labels and macros `board.dts` uses.

- A node the dtsi labels changes in `&label { }`; others change inside their nearest labelled
  ancestor, so no reference is a path.
- A node the dtsi disables and the board enables gets `status = "okay"`.
- A node disabled in both is not written. A node the board disables gets only
  `status = "disabled"`, plus whatever keeps references valid.
- A pin group or disabled node the board adds is dropped when nothing references it. An empty node
  the board adds on purpose is kept.
- A dtsi device the board lacks is disabled, not deleted.
- The distribution's own nodes (`ramoops`) are left out and named in the header.

The view orders properties so it compiles to the same blob: deletions first, then the dtsi's
properties (standard before vendor), children and aliases by name, then new properties in the
board's order, `status` last. Spellings are normalized when comparing: unit addresses and numbers
by value, macros evaluated, aliases by the node they name. Only headers whose names the view uses
are included. Each sunxi GPIO's pin is named in a comment (`/* PG18, PG19 */`).

**`--prove`** compiles the view against the same patched dtsi and compares it with `board.dtb` using
`canonical.py`, through one explicit projection of what a view may leave out:

- a disabled device's contents (the view only says it is off; its status value still counts),
- pin groups no enabled device selects,
- the distribution's nodes,
- labels (`__symbols__`),
- a missing `status` (counts as `okay`),
- unit-address spelling (`@00000000` is `@0`).

Anything else that differs fails the proof.

The header lists patches the view needs beyond its base kernel (the repository and tag or commit
the dtsi URL pins). They are found by name, so the list is best-effort: patches adding a node,
property or label the view uses, and patches adding a vendor compatible, rc-map name or property to
a driver or binding. A patch needed only by another listed patch is not named.

The base is the `soc` named by the `.translate.conf`. A board kept on its vendor kernel uses the
target base's `soc` and `soc-patches` instead, which may name a reference board file. A board's
`BOARD_KERNEL_DTB_UPSTREAM` overrides both, and `--soc <url>` tries another for one run (see
`trees.md` for choosing). The dtsi is read as cpp would splice it, with every header fetched from its
own tree. The proof compiles with `-@`, like the board's own build.

## board.dts and phandles

`factory_board.dts` keeps the blob's explicit `phandle` lines, so it decompiles back exactly.
`board.dts` does not: `build-dtb.sh` strips them, dtc numbers phandles itself, and `canonical.py`
must find the trees equal except for numbering, or the build stops. A raw phandle number cannot
survive into `board.dts`, since renumbering would change what it points at.

## Bindings

`bindings.py` copies the bindings of the kernel the tree is written against (the tag of the conf's
`soc` URL) and applies the binding changes from the kernel conf's patches, in order. Build the
schema from that and validate a dtb:

```sh
tools/dtcx/bindings.py <kernel tree> kernel/<kernel>.conf build/bindings
uvx --from dtschema dt-mk-schema -j -o build/schema.json build/bindings/Documentation/devicetree/bindings
uvx --from dtschema dt-validate -s build/schema.json boards/<board>/board.dtb
```

A patch that adds a compatible or property carries its binding in a `dt-bindings:` patch ahead of it
in the conf. Whatever the check still reports is what an upstream submission must answer; today,
only each board's own compatible.
