# Finish

## Do

1. **The full pass**: `system.md` to `input.md` again, on the family's kernel and on its `-next`,
   the Test report marked per kernel side by side. A number that differs between kernels is a
   finding.
2. **What remains**, off the Test report: each ❌ and each gap scoped in Known gaps: the vendor's
   code, the closest mainline driver, any series in flight, an estimate.
3. **A few days of daily use** by the human, every issue a worklog entry.
4. **The pull request.**

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

- [ ] **Q1** Every line has a mark on both kernels; no ❓ left
- [ ] **Q2** Every ❌ and gap is scoped in Known gaps
- [ ] **Q3** 👤 A few days of daily use with no issue
- [ ] **Q4** The README lists the board, in its support matrix too
- [ ] **Q5** CI is green
- [ ] **Q6** Untested platforms are named in the PR
