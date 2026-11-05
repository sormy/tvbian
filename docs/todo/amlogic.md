# Amlogic boards: what is left

What spans the family's boards.

- [ ] **Keep an Amlogic board's Ethernet address, as `LAN_MAC` is kept on Rockchip.** It is the
      unifykey `mac` slot, encrypted, so only the vendor U-Boot reads it (`keyman read mac`); the
      stock env hands it to Android as `mac=`. Our `aml_autoscript` runs in that U-Boot: read it,
      then `env export -t` `ethaddr` to fixed RAM for `boot.scr` to `env import` in the chained
      U-Boot, which sets `local-mac-address`. ❓ `env export` in this U-Boot; a RAM address neither
      relocates over.

- [ ] **No kernel self-tests in meson64.** 146 of its 4433 modules are KUnit and test modules, from
      Armbian's config: off in `kernel/meson64.fragment` (`CONFIG_KUNIT`), then a boot on the M20.
      The rest of its breadth stays: USB Wi-Fi, tuners and cameras are why a box is general.
