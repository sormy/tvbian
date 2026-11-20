#!/bin/bash
# Debian's packaging with WebRTC, which WPE builds without: on GStreamer's own WebRTC, so a call's
# video is encoded by GStreamer's encoders, the box's hardware ones among them; its ICE on librice,
# through the network process, so a call connects from inside the web process's sandbox. Run in the
# unpacked source by extras/build.sh.
set -euo pipefail
sed -i 's/^\t   -DUSE_LIBBACKTRACE=OFF$/\t   -DUSE_LIBBACKTRACE=OFF -DENABLE_WEB_RTC=ON -DUSE_GSTREAMER_WEBRTC=ON -DUSE_LIBRICE=ON/' debian/rules
grep -q -- '-DUSE_LIBRICE=ON' debian/rules
