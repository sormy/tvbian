# Extras from an upstream release

An extra today rebuilds Debian's own source with our patches. Some packages need a release Debian
does not have yet: Kodi 22, where trixie has 21.2 and sid 21.3. The same `extras/` directory takes
them, built from upstream's tag with packaging of our own, under Debian's package names so the day
Debian ships the release the extra turns back into an ordinary one.

## The two kinds

|               | Debian extra (today)       | Upstream extra                         |
| ------------- | -------------------------- | -------------------------------------- |
| Source        | `apt-get source $SOURCE`   | `$UPSTREAM` at `$TAG`                  |
| Packaging     | Debian's `debian/`         | `extras/<name>/debian/`, ours          |
| Version       | `<Debian's>+tvb<N>`        | `[epoch:]<upstream>-0tvb<N>`           |
| Moves when    | Debian's source moves      | `$TAG` moves, or `$TAGS` finds a newer |
| Ends when     | Debian carries every patch | Debian reaches the release             |
| Told apart by | no `UPSTREAM`              | `UPSTREAM` set                         |

`-0tvb<N>` sorts below Debian's own build of the same release (`22.0-0tvb1` < `22.0+dfsg-1`), so a
Debian upload of that release wins on a box until we rebuild it with our patches, as for a Debian
extra today. The epoch is Debian's: `kodi` is `2:`, so ours is `2:22.0~rc1-0tvb1`.

## `extra.conf`

```bash
# kodi: Kodi 22 on our FFmpeg; Debian has 21
SOURCE=kodi                      # Debian's source name: what the end check compares against
PACKAGE=kodi-bin                 # the package the plan finds the extra by
UPSTREAM=https://github.com/xbmc/xbmc.git
TAG=22.0rc1-Piers                # pinned; or TAGS, a regex, to float to upstream's newest
VERSION=2:22.0~rc1               # TAG in Debian's form, the epoch included
PATCHES="patches/kodi/0001-windowing-gbm-hand-the-display-to-a-program-run-by-S.patch
         patches/kodi/0002-cmake-apply-patches-of-the-caller-s-to-the-internal-.patch
         patches/kodi/0003-cmake-link-libcec-and-libdvdnav-into-kodi.patch
         patches/kodi/0004-VideoPlayer-v4l2request-device-options-from-the-disp.patch"
AFTER=                           # extras whose debs this one builds against
```

`TAGS` instead of `TAG` floats: `TAGS='^22\.[0-9]+(\.[0-9]+)?-Piers$'` takes the newest stable 22.
`VERSION` then derives from the tag by `VERSION_SED`; pinned, it is written out. Kodi starts pinned
on the release candidate and floats once 22.0 is out.

## Script by script

| Script              | Debian extra, unchanged | Upstream extra                                  |
| ------------------- | ----------------------- | ----------------------------------------------- |
| `extras/version.sh` | Debian's newest source  | `$TAG`, or the newest `git ls-remote` `$TAGS`   |
| `extras/carried.sh` | patches apply reversed  | Debian's `$SOURCE` ≥ upstream's                 |
| `extras/build.sh`   | `apt-get source`        | `git clone --depth 1 -b $TAG`, `debian/` copied |
| `release/inputs.sh` | conf, scripts, patches  | the same, `extras/<name>/debian/`, `AFTER`'s    |
| `release/plan.sh`   | `+tvb` count            | `-0tvb` count; the end message differs          |

- **`build.sh`** keeps one path past the source step: patches into `debian/patches/series`, the
  `X-Tvb-Inputs` field, a changelog entry, `dpkg-buildpackage -b`. The upstream changelog is the one
  entry it writes. `AFTER`'s debs, from `/out/debs`, are a local apt source for `build-dep`.
- **`carried.sh`** for an upstream extra exits 0 when Debian's `$SOURCE` is at or past the upstream
  version. The plan then prints "extra kodi: Debian's 2:22.0+dfsg-1 reaches 22.0; drop `UPSTREAM`,
  `TAG`, `VERSION` and `debian/`": the extra becomes a Debian one, and retires the usual way later.
- **`plan.sh`** passes `-0tvb` as the separator; `AFTER` orders the build and joins the dependent's
  inputs, so a new Kodi rebuilds its binary addons.
- **`./build.sh debs`** and `assemble` build extras in `AFTER` order.

## Kodi's packaging, ours

One source, the package names Debian's `kodi` uses for what we ship:

| Package           | Holds                                                                      |
| ----------------- | -------------------------------------------------------------------------- |
| `kodi-bin`        | `/usr/lib/kodi`, the binary, FFmpeg static                                 |
| `kodi-data`       | `/usr/share/kodi`, `Architecture: all`                                     |
| `kodi`            | depends on both                                                            |
| `kodi-addons-dev` | headers and CMake files; binary addons build on it, boxes never install it |

Debian's `kodi` provides a `kodi-api-<part> (= <version>)` per addon API, and its binary addons
depend on a range of one (`kodi-api-inputstream (>= 3.3.0), (<< 3.4.0)`). Ours provides Kodi 22's,
generated from `xbmc/addons/kodi-dev-kit/include/kodi/versions.h`: a Debian addon built for 21 then
installs only where Kodi's own API versions call it compatible.

## Open

- [ ] Build time on CI's arm64 runner: a release job builds extras in turn, inside its 360 minutes.
      Past about an hour, Kodi gets its own job, as a kernel does.
- [ ] ccache for extras: `/usr/lib/ccache` on `PATH` in `build.sh`, the kernel's cache directory.
- [ ] Kodi's CMake downloads its internal libraries, each pinned by SHA-512 in its `VERSION` file:
      the build needs the network, as a kernel's does for its tag.
- [ ] `release/guard.sh` on a first upstream extra: every path is new to the published index.
- [ ] `tests/`: `version.sh` and `carried.sh` for both kinds; the plan's line for each state.
