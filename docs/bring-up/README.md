# Bringing up a box

An agent brings a TV box up to TVBian with the human's hands only where a step needs them. This
folder is the whole procedure: this file, read whole first, then one phase at a time.

| Kind   | When                                    | Files, in order                                       |
| ------ | --------------------------------------- | ----------------------------------------------------- |
| board  | family and chips in the repo            | contact to input in the table below, then `finish.md` |
| chip   | a Wi-Fi, BT or other chip has no driver | as a board, with `chip.md` before `finish.md`         |
| family | the SoC family is new                   | `contact.md`, `family.md`, then as a board            |

**A board of a known family with known chips is mostly authoring**: its trees (`trees.md`) and its
board data (`boot.md`). Validation leans on its sisters: a line whose block is a sister's ✅ needs
only a weak check here. The effort goes where this board differs from them: its wiring, RAM, eMMC,
ports, remote and LEDs, and its heat: sisters by block are not sisters by heat, and a stick runs
hotter than its box sibling.

| File          | Covers                                                    |
| ------------- | --------------------------------------------------------- |
| `contact.md`  | photos, a way in, the SoC read off the box, the kind      |
| `backup.md`   | the full eMMC image, the DRAM-init blobs, a way back      |
| `identity.md` | the board ID, its components, `board.md`, the serial pins |
| `dump.md`     | the stock firmware as files, the factory trees, the bases |
| `trees.md`    | the board's kernel and U-Boot trees                       |
| `boot.md`     | board data, RAM first, a first boot, install, changes     |
| `system.md`   | boot, reboots, RAM, the watchdog, crash records, heat     |
| `video.md`    | decode, encode, the picture path from decoder to screen   |
| `display.md`  | HDMI, audio, CEC, DDC, the AV jack, the GPU               |
| `power.md`    | sleep, wake, off, draw                                    |
| `storage.md`  | eMMC, SD, install, the service mode on our U-Boot         |
| `network.md`  | Ethernet, Wi-Fi, Bluetooth, addresses                     |
| `input.md`    | USB, the remote, buttons, LEDs                            |
| `chip.md`     | a driver for a chip that has none                         |
| `family.md`   | what every board of a new family inherits                 |
| `finish.md`   | the full pass on both kernels, the pull request           |

## The run

Each phase is **Do**, the steps in order; **Bites**, the traps that cost earlier bring-ups hours;
and **Check**, its lines. The agent reads one phase whole, does it, then runs every Check line and
records it before the next phase starts. A phase is done when each of its lines has a mark.

**State lives in files, never in memory**, so a run resumes from them:

| File                      | Holds                                               |
| ------------------------- | --------------------------------------------------- |
| `docs/<board>/board.md`   | the Test report: every line's ID, mark and evidence |
| `docs/<board>/worklog.md` | dated: what was tried, the command, what it showed  |
| `build/logs/<board>/`     | every serial and test log, one file per attempt     |

What remains is read off the Test report: every line not ✅, ➖ or a recorded ❌. A line's ID lives
in this folder and the Test report alone; the worklog, commits and messages name what it checks.

**A box that resets itself comes first.** The watchdog and the kernel's lockup detectors
(`system.md`) are what let the agent run unattended: a hang it causes resets the box, and the next
attempt starts in a minute instead of waiting for someone to pull the power. Until they hold, every
hang is a human's step.

**The agent runs unattended**, in a loop such as Claude Code's `/loop`. It asks the human for:

- a 👤 line's action, batched with the other waiting ones, one action at a time: what to wire, press
  or look at, why, and what to report back;
- a choice with a real trade-off, stated once; the human's choice wins;
- consent before writing the eMMC's bootloader on a box whose way back is not proven.

Everything else it does. 👤 lines wait for one batch at the end, except those a phase needs to go
on: the first way in, the backup's read, a first boot from external media. **Fewest human actions
first**: a cable beats a click-through, and a guess costs the human a power cycle.

**It stops and reports** when one step has failed three times with three different fixes, when the
box answers on no way in, or when the next step would cost the only way back.

**It never parks on a timer.** While a build runs it does the work that does not need it; it wakes
on the build's completion, not on a schedule. When the human changes the plan, every pending wakeup
or loop carrying the old one is cancelled in the same turn.

## Working the box

These hold in every phase.

**Evidence.**

- Every claim to the human carries its evidence: the log's path and the lines it rests on. A cause
  or a limit is "likely" until the command that shows it has run.
- Read a log whole before naming an event in it. A console that does not answer proves nothing until
  the log shows the box alive at a prompt.
- A request granted is not an effect: a property set, a framebuffer accepted, a command that
  returned 0. Read the result back.
- A verify fails on nothing: compare a byte count before a hash; two empty streams hash alike.
- A cause is toggled, not caught once: the symptom follows the suspect on and off twice each way
  before a fix is written. Before blaming a tree property, read what the driver does with it.
- A fix to a block several outputs share (a clock, a pad, a TCON) is checked on every output it
  serves, from a cold boot with each connected.

**Logs.**

- One reader per serial port: the human's terminal or the agent's logger, never both.
- Every boot gets a new file, `build/logs/<board>/<YYYYMMDD-HHMMSS>.log`, opened before power-on,
  every line timestamped. A running tool's log file is buffered: read the port, or the file once the
  tool has closed it.

**Safety.** A working box is the expensive one to lose.

- A tree or kernel change boots from RAM over the service mode first, or with a one-boot argument
  typed at U-Boot's prompt, never written to the boot config.
- A second way in, USB Ethernet or serial, is plugged in before a kernel swap.
- Nothing replaces the eMMC's bootloader on a box whose way back is not proven.

**Builds.** Everything goes through `./build.sh` from the first artifact: it brings the cache, the
host's CPUs and memory. A scratch script is a bug to remove the same day; one container holds the
build volume at a time; a script is never edited while it runs. Even a one-module change builds on
the host and goes to the box built: a stick or a small box with poor cooling compiles slowly,
throttles, and its heat disturbs what is being measured. A box with the headroom may build; the host
is still the default. Iterate with host-built modules or a kexec'd kernel; a full redeploy is the
final smoke test only.

**Experiments fail fast.** Every run has a hard cap and exits the moment the answer is known; its
worst case is stated before it starts. An event is driven, never waited for: a test access point
with `wpa_group_rekey=20`, not a router's hourly rekey. While something long runs, the work that
doesn't need it goes on, and its completion wakes the next step, not a timer.

**An intermittent fault**, in this order: the journal's timeline around every occurrence, each
driver warning in it traced to its source and to any handling the vendor commented out; a scenario
that forces it in minutes; a fix at the first event of the chain, a workaround only after. A
measuring tool is proven on one known event before it is trusted. Soaking until it happens again is
the last resort.

**Bring-up integrates; research digs.** A driver from scratch, or a fault that needs a study, goes
to `research/<experiment>/`; the board ships with the gap marked and scoped.

## Marks

A mark is confidence that the line works, not a record of which test ran. Even ✅ is not proof: only
months of daily use proves a board, and a ✅ that fails later turns ❌, the case in the worklog.

| Mark | Means                                                |
| ---- | ---------------------------------------------------- |
| ✅   | verified here, or a weak check here on a sister's ✅ |
| 🟡   | a weak check passed, nothing against it              |
| ❓   | not checked at all                                   |
| ❌   | tested and broken                                    |
| ➖   | not on this box                                      |

- **A weak check** is the same mechanism ✅ on a similar board. A node that probes, or a connector a
  driver lists, is no check: a port is ❓ until its output is seen or heard.
- **A sister** is identical for that block: the same SoC, chip and tree node. A line turning ✅
  turns its sisters' weak-checked 🟡 ✅ in the same pass.
- **Hardware the box has and mainline lacks** is a scoped to-do, not ➖: the vendor's code, the
  closest mainline driver, any series in flight, an estimate.
- **A trade-off the hardware forces** ships as a switch the user sets at runtime, its default the
  common case, never one side left out of the build.

## Kit

| Item                                   | For                                      |
| -------------------------------------- | ---------------------------------------- |
| multimeter, any cheap one              | finding the serial pins                  |
| TTL adapter: 1.8/3.3/5 V jumper, FT232 | serial; a CP2102 cannot do 1.5 Mbaud     |
| test hooks, or a soldering iron        | holding the serial pads                  |
| USB-A male-to-male cable               | the USB service mode                     |
| USB Ethernet adapter, RTL8152/8153     | a network before the board's own         |
| a power switch the host toggles        | power cycles without hands               |
| USB camera                             | the agent watching the screen            |
| TV with CEC; PC monitor with DDC/CI    | the HDMI checks                          |
| 3.5 mm AV to 3×RCA, RCA to HDMI        | the AV jack's picture on any HDMI screen |
| stereo headphones; S/PDIF to RCA       | the AV jack's and S/PDIF's audio, by ear |
| AV receiver, where there is one        | passthrough                              |
| SD card, USB stick, SSD in a USB case  | booting images; the USB stress test      |
| power meter                            | draw at idle, suspended and off          |
