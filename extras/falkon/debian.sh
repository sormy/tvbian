#!/bin/bash
# Debian's packaging built on WPE WebKit: the build switched over, and GStreamer's playback plugins
# depended on in place of QtWebEngine's QML module, which the WPE build does not load. Run in the
# unpacked source by extras/build.sh.
set -euo pipefail
sed -i 's/^\tdh_auto_configure$/\tdh_auto_configure -- -DFALKON_WPE=ON/' debian/rules
grep -q -- '-DFALKON_WPE=ON' debian/rules
# WebKit plays media and calls through GStreamer: VA's decoders and WebRTC are in -bad, its zero-copy
# sink in -gl, a call's connectivity in -nice
sed -i 's/^ qml6-module-qtwebengine,$/ gstreamer1.0-plugins-base, gstreamer1.0-plugins-good, gstreamer1.0-plugins-bad, gstreamer1.0-gl, gstreamer1.0-nice,/;
  /^Suggests:$/,/^ libqt6webenginecore6-bin$/d' debian/control
sed -i 's/^Description: lightweight web browser based on Qt WebEngine$/Description: lightweight web browser based on WPE WebKit/;
  s/ very fast Qt Webengine browser\./ very fast WPE WebKit browser./' debian/control
# WebKit spellchecks with Hunspell's dictionaries
sed -i 's/^ libsvtav1enc0$/ libsvtav1enc0, hunspell-en-us | hunspell-dictionary/' debian/control
grep -q 'hunspell-dictionary' debian/control
! grep -qi webengine <(sed -n '/^Package: falkon$/,/^$/p' debian/control)
