# Regression

The bring-up's validation, `system.md` to `input.md`, run again on what a change can break: a
kernel, a patch, a tree, a package. Every board the change reaches, on both kernels, before the
change is reviewed. It is the full pass of `finish.md` minus what no change touches, and the same
tools: a line that differs from the board's last run is a finding.

## Do

1. **Before a tree boots**, for a translated board, `conversion.md`'s checks: `semdiff.py` against
   the last proven tree, `upstream.py --prove`, `dt-validate` against the patched bindings. A
   board's tree is rebuilt from its patch, `build-dtb.sh`, the patch reproducing it.
2. **Run the suite on the boxes, which run it alone**:
   `tools/validate/regression.py run [--profile short|default|extended] BOARD=USER@HOST ...`
   deploys, waits, collects and reports. Deploy installs the family's kernels, the tools and the
   board's package built fresh from this tree; a box that fails to install is not run. The host
   checks what needs the repo: the box runs the repo's tree, and its upstream view proves. Then it
   copies the suite to the box and starts it; a systemd unit runs `onbox.py` at
   every boot. It boots each kernel of the family, the family's and its `-next`, with a guard that
   brings the default back if the kernel brings no network up (`boot.md`). On each it runs the
   profile, every check unattended, none left out for what the change touched:
   - **`short`, a smoke test, every board the change reaches**: each kernel booted, then every
     `box.py` phase except `throughput` at short timings, the composite check and a 1080p hardware
     decode. No `iperf3`, so several boxes may run it at once.
   - **`default`, one box per hardware block**: the phases with `throughput`, composite, and
     `video.py`'s decode suite at a sample of sizes: 1080p, 4K, 4096 wide and 8K. Boards that share a
     SoC, its kernel and the engine's tree nodes (the 3518, 3518D, R69-1 and M2 Plus) need it on one;
     the rest get `short`. A board whose tree changed gets `default` itself.
   - **`extended`, a release or a kernel series**: the same at bring-up's timings, with a sleep past
     the watchdog, then the 30-minute soak, `display.py` whole, `screen.py`, the whole video matrix,
     dEQP against Mesa CI's lists, a panic and an unpinged watchdog that must each bring the box
     back, and 5 warm reboots.

   The boxes need no session: a driver reload, a reboot or a hang ends nothing. `collect` fetches
   each box's results whenever it answers; the box restores its default and stops when done.

3. **Report**: `regression.py report build/validate/regression/<date>` writes `report.md` there, for
   the pull request: each board and kernel with its checks and minutes, new failures apart from the
   known ones in `tools/validate/known.conf`, every ❓, and what moved since the board's last run.
   Attach it to the PR. A new ❌ is a finding; a known one stays known only with its reason, and its
   line goes when the fix lands.
4. **Record** each kernel's lines in the board's Test report and a worklog entry: the lines that
   moved, and why.
5. **Hand the human** the lines below that the change reaches, each with what to look for.

## What needs hands

The unattended pass proves a device answers; these need a person, a screen or a plug.

| Item                      | What the human confirms                                     | Phase        |
| ------------------------- | ----------------------------------------------------------- | ------------ |
| The remote, every button  | each key as its printed label (`docs/remote-keymap.md`)     | `input.md`   |
| HDMI on a real screen     | picture at the TV's modes, EDID read, CEC to the TV         | `display.md` |
| Sound from a speaker      | audible, both rates; the pass proves only the rate          | `display.md` |
| The AV jack               | composite picture, analog sound                             | `display.md` |
| USB ports and the SD slot | a device on each port, a card in and out                    | `storage.md` |
| Buttons and LEDs          | power and recovery buttons, each LED's colour and state     | `input.md`   |
| Sleep and wake            | wake by the remote and the power key; the pass wakes by RTC | `power.md`   |
| A BLE remote              | pairs, keys, survives a power cycle                         | `network.md` |
| An Ethernet cable         | link at its speed, where the pass found no cable            | `network.md` |

## Bites

- **A pass must not hang on what it measures against**: an `iperf3` server that does not answer
  stopped one; every network step has a timeout.
- **The `iperf3` server is this machine unless named**: `--iperf HOST`, a name the box resolves;
  unnamed, `regression.py` serves here, at its IPv4 address on the route to the box. Never a
  written address: addresses drift.
- **Each link is measured through itself**: `iperf3 --bind-dev` the interface, whatever the
  server's address family; unbound, a box with a cable measures the cable under the radio's name.
- **The `iperf3` server takes one box at a time**: `default` and `extended` run one box at a time;
  `box.py` only retries a busy server, there is no lock across boxes. The soak pings instead. A
  box that finds the server busy measured another box's test, not its own radio.
- **A missing tool is a line, not a gap**: a box without `bluetoothctl` or `iperf3` says so; a
  number that is not there is not a pass.
- **Measure a settled box**: the first boot after an install runs setup, and a player left running
  skews every number; `box.py` waits for the CPU to idle.
- **A reboot is a new `boot_id`**, not an answered ping: a box that never went down answers too.
- **A refused reboot is not a lost box**: `systemctl reboot` as a user is refused without a word;
  `reboots.sh` reboots through `sudo -n`.
- **A box that stops answering by `.local` may be up**: avahi that loses a name race renames the box
  (`h96max-m20-2.local`); try the bare name before calling it lost.

## Check

- [ ] **R1** Each translated board's tree passes `conversion.md` V3 to V5
- [ ] **R2** `regression.py deploy`, both kernels: `short` on every board the change reaches,
      `default` on one per hardware block and on each board whose tree changed, `extended` for a
      release; `report.md` on the PR, each new ❌, ❓ and moved line explained
- [ ] **R3** `reboots.sh`, 5 on each kernel, every boot back with its radios and no MMC error
- [ ] **R4** `video.py compare` against the last run: nothing worse
- [ ] **R5** The hands-on lines the change reaches, handed to the human with what to confirm
