#!/bin/sh
# The greeter, under labwc: kanshi scales each screen plugged in; labwc goes when gtkgreet does
kanshi -c /usr/share/tvb-desktop/kanshi.conf &
gtkgreet -l -s /usr/share/tvb-desktop/greeter.css -c /usr/libexec/tvb-desktop/session
labwc --exit
