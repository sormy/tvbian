# Display, audio, GPU

## Do

1. **Modes** on a TV and a PC monitor, switched at runtime with `modetest -s`, never by rebooting;
   `kmscube` on screen with its stdin held open (`sleep 60 | kmscube`).
2. **HDR and frame rate**: every transition a player makes at one mode, SDR to HDR, film to film,
   back, proven by the InfoFrame read back from the HDMI controller; the refresh following the
   content's 23.976, 24, 25 or 50 fps.
3. **Audio**: every sound card times 3 s in 3 s (`tools/validate/validate.sh`).
4. **The AV jack and S/PDIF** through the kit's adapters: the composite picture on an HDMI screen,
   the jack's audio in headphones. First find the jack's ground: the RCA that beeps to a USB shell,
   box off. A cable grounded elsewhere gives no picture; the CTIA-to-OMTP adapter fixes it. Video
   can still sit on another plug: colour bars on composite, each plug in turn in the video input.
   **Composite is `Composite-1`, off by default**: the connector of type Composite, a driver that
   names it otherwise patched; `video=Composite-1:d` in `BOARD_CMDLINE`, else it sizes the console
   when HDMI is plugged in after boot. Turn it on for the test with
   `echo on > /sys/class/drm/card0-Composite-1/status`, and `off` after.
5. **The GPU** headless first, EGL on GBM rendering to an FBO, `glReadPixels` on a known triangle;
   then on screen with the full default `glmark2-es2-drm` suite, beside a sibling family's full run.
6. **Planes**: every plane the CRTC offers, with its formats, compression, scaling, alpha and zpos.
   Then a video plane under the interface, composed by the engine with no GPU pass, at the native
   mode and at 4K, with no underrun. Then a minute of a player's commits: nonblocking, each after
   the last flip, the video scaled.
7. **Hardware tone mapping**: each colour stage (a 3D table, EOTF and OETF tables, a matrix), per
   plane and per CRTC, exposed as a property. Its output by writeback matches the same table
   computed on the host, or, with no writeback, its registers read back. Record which planes each
   stage maps and what the engine cannot do, so the player knows when to use the GPU.
8. **Unattended**: `tools/validate/display.py` runs steps 6 and 7 and the HDR side of step 2, with
   HDMI unplugged: synthetic EDIDs stand in, and a real screen's gets in their way. Only the picture
   on a real HDR screen needs a person.

## Bites

- **Memory bandwidth can be the bottleneck**: every plane scans out of RAM each frame, beside the
  decoder. Dropped frames that come with more planes or a larger mode are checked against the
  board's Memory row first.
- **Anything that looks off is a bug**: a missing mode, a wrong rate, a console font too big or too
  small. Known here: no 4K on Rockchip without the line-buffer graft; a 2K monitor's native mode
  pruned until a kernel patch; the console font set by the kernel config.
- **A picture that drops**: swap the cable first.
- **CEC needs no TV**: `cec-ctl` reads a physical address from a monitor's EDID.
- **The GPU is judged on screen**, never off-screen or on a subset. A scene far off its siblings is
  a wiring fault until shown otherwise.
- **Half-speed audio needs no ears**: a timed playback finds it.
- **HDR out needs a screen that lists it**: Rockchip sends the HDR InfoFrame only for an EOTF the
  EDID lists; mainline sends it regardless. On a forced connector, Rockchip updates InfoFrames only
  when the output comes up.
- **Know each stage's scope**: Rockchip's SDR to PQ maps every plane, HDR video included; the H616's
  CDC maps only its own plane.
- **Match vendor tables byte for byte**: replace a vendor library's register data only with a
  generator that reproduces it exactly.
- **An early flip event refuses the next commit**: on the Tanix it cost a dropped picture each time.
- **4K60 is a rating, not a mode list**: an offered mode can still underrun or fall behind with
  full-size planes.
- **A stage counts only once writeback shows it**: vendor tables list stages the chip lacks, as the
  H313's channel 1 CDC and the S905L3's OSD EOTF and OETF.

## Check

- [ ] **H1** 👤 A TV at the largest mode the box claims, 8K60 where the kit's TV shows it, 4K60 on
      most: picture and sound, replugged, its remote over CEC; a claim past the TV stays ❓
- [ ] **H2** 👤 Optional: every refresh rate and 1440p on a TV, and a PC monitor's modes
- [ ] **H3** Every HDR transition at one mode, the InfoFrame read back, on an HDR screen or the
      synthetic one (`hdmi`)
- [ ] **H4** 👤 Optional: the refresh follows the content's frame rate; VRR, QMS and ALLM where
      offered
- [ ] **H5** Every sound card plays a timed 3 s in 3 s, at 44.1 and 48 kHz
- [ ] **H6** 👤 Optional: multichannel LPCM plays
- [ ] **H7** 👤 Optional: AC3 and DTS pass through to a receiver
- [ ] **H8** `cec-ctl` shows a physical address
- [ ] **H9** `ddcutil getvcp 10` reads a monitor's brightness
- [ ] **H10** `ddcutil setvcp 10` moves it
- [ ] **H11** 👤 Optional: S/PDIF out, heard
- [ ] **H12** 👤 Optional: AV out, a picture, and the jack's audio heard
- [ ] **H13** The GPU's full `glmark2-es2-drm` suite on screen, beside a sibling family's
- [ ] **H14** The console font reads right at the native mode
- [ ] **H15** Every plane's formats, compression, scaling, alpha and zpos listed (`planes`)
- [ ] **H16** A video plane under the interface, composed by the engine, native mode and 4K, no
      underrun (`compose`, `underruns`)
- [ ] **H17** Each colour stage a property, its writeback within two codes of the host's table, or
      its registers read back (`lut`, `sdr2hdr`)
- [ ] **H18** A minute of player-paced nonblocking commits, none refused (`pacing`)
- [ ] **H19** An SDR interface over HDR video: the interface mapped, the video untouched, or the
      whole-output scope recorded (`scope`)
- [ ] **H20** What the engine cannot map, recorded for the player's GPU path (`RECORD maps`)
- [ ] **H21** SDR, HDR10, HLG and HDR10-and-HLG screens: HDR sent for what each lists (`sinks`)
- [ ] **H22** The display's rating, its largest and fastest sustained modes, in `board.md`
      (`rating`)
