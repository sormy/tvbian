#!/bin/sh
# The desktop session. greetd starts it outside the systemd user manager, so it takes the environment
# that manager's generators give a login itself: environment.d's, and each package's, as
# tvb-va-driver's per-SoC choice of GStreamer's decoders. Then labwc.
for generator in /usr/lib/systemd/user-environment-generators/*; do
    [ -x "$generator" ] || continue
    # each prints KEY=VALUE lines, taken as they are, never run as shell
    "$generator" | while IFS= read -r assignment; do
        case $assignment in [A-Za-z_]*=*) printf '%s\n' "$assignment" ;; esac
    done
done >"${XDG_RUNTIME_DIR:-/tmp}/tvb-desktop-environment"
while IFS= read -r assignment; do
    export "$assignment"
done <"${XDG_RUNTIME_DIR:-/tmp}/tvb-desktop-environment"
exec labwc
