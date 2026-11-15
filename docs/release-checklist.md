# Shipping a package through the release

What a package needs to build, take its version and publish, through `./build.sh release` on a host
and the `Release` workflow in CI. A package that misses one builds on a Mac and never ships, or
ships and never rebuilds.

## An extra

A Debian package rebuilt with our patches, or an upstream release beside Debian's, in
`extras/<name>/`. The plan and CI find every `extras/*/extra.conf` themselves.

- [ ] `extra.conf` names `PACKAGE`, the binary the plan looks the extra up by; `SOURCE`, Debian's
      source package, when it differs; `VERSION` only for an upstream release, which skips Debian's.
- [ ] Every patch is in `PATCHES`, one path a line. The version moves when `extra.conf`,
      `extras/<name>/build.sh` or a listed patch does, nothing else: a file the build reads from
      anywhere else changes nothing published.
- [ ] An upstream release's own `build.sh` writes its runtime libraries into `Depends`, and adds a
      library it links to both its build and its runtime lists.
- [ ] The plan sees it:

  ```sh
  ./build.sh plan    # host: a line "extra <name> <version> new" in build/out/release/plan
  ```

- [ ] It builds alone:

  ```sh
  ./build.sh extra <name>    # host: its debs in build/out/debs/
  ```

- [ ] A path it ships that another package shipped before gets `Replaces` and `Breaks` on it;
      `./build.sh release` runs the guard that fails otherwise.
- [ ] An image that should carry it lists it in `base/package.list` or the board's own.
- [ ] Once Debian carries every patch, the plan writes `extra <name> retired`: delete
      `extras/<name>/`.

## A new kind of package

A package that is not an extra, built by a step of its own, as `va-driver/` is. Everything above
applies, and the wiring an extra gets for free has to be added by hand:

- [ ] `build.sh`: the step in the list of steps it accepts, the usage line, the loop of `debs` and
      the `case` of `assemble` that builds what the plan calls new.
- [ ] `release/plan.sh`: one `plan` line per package, with its step, argument, package name and
      inputs.
- [ ] `release/inputs.sh`: every file the build reads, sources and confs alike, and the versions of
      the tools that shape its bytes, the compiler for code.
- [ ] `.github/workflows/release.yml`: its directory in both `paths` lists, `push` and
      `pull_request`. Missing there, a change to it alone starts no run, and the package waits for
      the weekly one.
- [ ] Its tests under `tests/`, which CI's `test` job runs; a check outside it runs on a host only.

Before its first release each of its plan lines reads `new`; after it, a second `./build.sh plan`
reads `published`.
