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
   box off. A cable grounded elsewhere gives no picture; the CTIA-to-OMTP adapter fixes it.
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
8. **Unattended**: `tools/validate/display.py` runs steps 6 and 7 and the HDR side of step 2. With
   no HDR screen, a synthetic EDID stands in. Only the picture on a real HDR screen needs a person.

## Bites

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

- [ ] **H1** 👤 1080p at every refresh rate, on a TV
- [ ] **H2** 👤 1440p at every refresh rate, on a TV
- [ ] **H3** 👤 4K at every refresh rate, on a TV
- [ ] **H4** 👤 The same modes on a PC monitor
- [ ] **H5** 👤 Hotplug re-detects, with no blank screen after
- [ ] **H6** Every HDR transition at one mode, the InfoFrame read back, on an HDR screen or the
      synthetic one (`hdmi`)
- [ ] **H7** 👤 The refresh follows the content's frame rate; VRR, QMS and ALLM where offered
- [ ] **H8** Every sound card plays a timed 3 s in 3 s, at 44.1 and 48 kHz
- [ ] **H9** 👤 HDMI audio plays, as the default sink
- [ ] **H10** 👤 Multichannel LPCM plays
- [ ] **H11** 👤 AC3 and DTS pass through to a receiver
- [ ] **H12** `cec-ctl` shows a physical address
- [ ] **H13** 👤 Mute and volume on the TV remote reach the box
- [ ] **H14** `ddcutil getvcp 10` reads a monitor's brightness
- [ ] **H15** `ddcutil setvcp 10` moves it
- [ ] **H16** 👤 S/PDIF out, heard
- [ ] **H17** 👤 AV out: a picture, and the jack's audio heard
- [ ] **H18** The GPU's full `glmark2-es2-drm` suite on screen, beside a sibling family's
- [ ] **H19** The console font reads right at the native mode
- [ ] **H20** Every plane's formats, compression, scaling, alpha and zpos listed (`planes`)
- [ ] **H21** A video plane under the interface, composed by the engine, native mode and 4K, no
      underrun (`compose`, `underruns`)
- [ ] **H22** Each colour stage a property, its writeback within two codes of the host's table, or
      its registers read back (`lut`, `sdr2hdr`)
- [ ] **H23** A minute of player-paced nonblocking commits, none refused (`pacing`)
- [ ] **H24** An SDR interface over HDR video: the interface mapped, the video untouched, or the
      whole-output scope recorded (`scope`)
- [ ] **H25** What the engine cannot map, recorded for the player's GPU path (`RECORD maps`)
- [ ] **H26** SDR, HDR10, HLG and HDR10-and-HLG screens: HDR sent for what each lists (`sinks`)
- [ ] **H27** The display's rating, its largest and fastest sustained modes, in `board.md`
      (`rating`)
