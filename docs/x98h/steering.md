# x98h — steering

Where the docs, the rules or our own search steered wrong.

## The panel node was in the tree all along — `missing`/`agent`

- **Found by:** the PR's reviewer, who pointed at the in-tree `tm16xx` driver.
- **Cost:** most of a day building a userspace driver that should not exist.
- **What happened:** the vendor tree's node is `amediatech,yxt_vfd`. We searched the decompile for
  `seg`, `segment`, `gpio-leds` and `led` and found nothing, then concluded the pins had to be
  discovered empirically. Searching for the *chip family* (`sm1628`, `tm1628`, `vfd`) finds it in
  one grep.
- **Fix (asked for):** when a panel or button block has no obvious node, search the decompile for
  the driver's own vocabulary — chip part numbers and vendor prefixes — before concluding it is
  absent. The driver's `strings` on the box are the second place to look.

## The bring-up procedure assumes a way in this box never had — `doc`

- **Found by:** the agent, reading `docs/bring-up/` after the PR was rejected.
- **Cost:** the PR was submitted as a plain board entry with none of the phase files, and could not
  be merged.
- **What was missing:** nothing in the procedure says what a board entry looks like when there was
  **no stock shell and no serial**: `import.md` covers no box in hand, `otg.md` covers no serial,
  but "box in hand, no serial, no stock shell" falls between them, and the answer we settled on
  (take the image, boot external media, then wire serial) is not written down.
- **Fix (asked for):** a line in `README.md` for that combination, or a short doc naming the order.

## A GPU claim without the renderer's name is worthless — `tooling`

- **Found by:** a measurement that was 30× slower than the same work on a sibling.
- **What happened:** on the sibling H616 box `panfrost` fails to probe at boot (`deferred probe
  timeout … -110`), `/dev/dri` has only `card0`, and Mesa falls back to **llvmpipe** without an
  error. The measurement ran on the CPU and looked like "the GPU is slow".
- **Fix:** record the renderer beside every GPU number (`equirect2flat --info` prints it), and
  reload the module (`modprobe -r panfrost && modprobe panfrost`) after a boot before trusting it.
