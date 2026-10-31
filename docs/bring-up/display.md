# Display, audio, GPU

## Do

1. **Modes** on a TV and a PC monitor, switched at runtime with `modetest -s`, never by rebooting;
   `kmscube` on screen with its stdin held open (`sleep 60 | kmscube`).
2. **HDR and frame rate**: every transition a player makes at one mode, SDR to HDR, film to film,
   back, proven by the InfoFrame read back from the HDMI controller; the refresh following the
   content's 23.976, 24, 25 or 50 fps.
3. **Audio**: every sound card times 3 s in 3 s (`tools/validate/validate.sh`).
4. **The AV jack and S/PDIF** through the kit's adapters: the composite picture on an HDMI screen,
   the jack's audio in headphones.
5. **The GPU** headless first, EGL on GBM rendering to an FBO, `glReadPixels` on a known triangle;
   then on screen with the full default `glmark2-es2-drm` suite, beside a sibling family's full run.

## Bites

- **Anything that looks off is a bug**: a missing mode, a wrong rate, a console font too big or too
  small. Known here: no 4K on Rockchip without the line-buffer graft; a 2K monitor's native mode
  pruned until a kernel patch; the console font set by the kernel config.
- **A picture that drops**: swap the cable first.
- **CEC needs no TV**: `cec-ctl` reads a physical address from a monitor's EDID.
- **The GPU is judged on screen**, never off-screen or on a subset. A scene far off its siblings is
  a wiring fault until shown otherwise.
- **Half-speed audio needs no ears**: a timed playback finds it.

## Check

- [ ] **H1** 👤 1080p at every refresh rate, on a TV
- [ ] **H2** 👤 1440p at every refresh rate, on a TV
- [ ] **H3** 👤 4K at every refresh rate, on a TV
- [ ] **H4** 👤 The same modes on a PC monitor
- [ ] **H5** 👤 Hotplug re-detects, with no blank screen after
- [ ] **H6** Every HDR transition at one mode, the InfoFrame read back
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
