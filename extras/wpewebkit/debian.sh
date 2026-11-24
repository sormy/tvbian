#!/bin/bash
# Debian's packaging with WebRTC, which WPE builds without: on GStreamer's own WebRTC, so a call's
# video is encoded by GStreamer's encoders, the box's hardware ones among them; its ICE on librice,
# through the network process, so a call connects from inside the web process's sandbox. No spell
# checking: Enchant and its dictionaries load with every browser start, too dear on these boxes.
# Precompiled headers without a timestamp, so the compiler cache can keep the files built with them.
# Run in the unpacked source by extras/build.sh.
set -euo pipefail
sed -i 's/^\t   -DUSE_LIBBACKTRACE=OFF$/\t   -DUSE_LIBBACKTRACE=OFF -DENABLE_WEB_RTC=ON -DUSE_GSTREAMER_WEBRTC=ON -DUSE_LIBRICE=ON -DENABLE_SPELLCHECK=OFF/' debian/rules
grep -q -- '-DENABLE_SPELLCHECK=OFF' debian/rules
sed -i '1a export DEB_CXXFLAGS_MAINT_APPEND += -Xclang -fno-pch-timestamp' debian/rules
grep -q -- '-fno-pch-timestamp' debian/rules
