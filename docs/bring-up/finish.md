# Finish

## Do

1. **The full pass**: `system.md` to `input.md` again on the family's kernel. On its `-next`, the
   unattended lines a kernel can change, in their own table: the image, the bootloader, the hardware
   and the hands-on lines are marked once. A number that differs between kernels is a finding.
2. **What remains**, off the Test report: each ❌ and each gap scoped in Known gaps: the vendor's
   code, the closest mainline driver, any series in flight, an estimate.
3. **A few days of daily use** by the human, every issue a worklog entry.
4. **The post-mortem**: each `steering.md` entry becomes its fix in `docs/bring-up/`, `AGENTS.md` or
   a test, the commit named in the entry; then the file goes.
5. **The README rows**: the main README's and the family's, one Hardware cell in both, every item
   from `board.md`, none with a ❓; and the family's Memory row:

   ```text
   SoC · RAM type · eMMC mode · SD mode or no SD · USB (OTG) · LAN or no LAN · chip Wi-Fi + BT or BLE · HDMI · AV · IR
   ```

6. **The pull request.**

## Bites

- **One board, one PR**: tree, data, docs and patches, however large. A chip may follow in its own
  PR, the board landing with it ❌.
- **An AI reviews it** for structure and content, not form: a factory-derived tree is not rewritten
  to look hand-made.
- **Kernel patches stay focused**, one fix each in `patches/<upstream>/` with its status: every
  board on that kernel takes them.
- **A board's own kernel or kernel patch** needs a reason the family's cannot meet, in its
  `board.md`.

## Check

- [ ] **Q1** Every line has a mark, `-next` lines too; no ❓ left, optional lines aside
- [ ] **Q2** Every ❌ and gap is scoped in Known gaps
- [ ] **Q3** 👤 A few days of daily use with no issue
- [ ] **Q4** The main README and its family's README list the board, one Hardware cell in both
- [ ] **Q5** CI is green
- [ ] **Q6** Untested platforms are named in the PR
- [ ] **Q7** Every `steering.md` entry names the commit that fixed it
