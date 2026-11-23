# Rockchip MPP patches

`tvb-va-driver` links libmpp in statically and loads on every board. libmpp ran its platform probe
from a constructor as it loaded: every process read the device tree, and off Rockchip each one
logged "can not found match soc name". `0001` makes the probe a call, which the driver makes only
after it finds `/dev/mpp_service`. `va-driver/build.sh` applies it to MPP at the commit it pins.

| Patch  | Fixes                                                | Upstream |
| ------ | ---------------------------------------------------- | -------- |
| `0001` | the platform probe and its log line in every process | not sent |
| `0002` | IEP2 deinterlace dropping fields at a stream's edges | not sent |

`0002`: IEP2 deinterlace gives two pictures for each interlaced one, but stock MPP lost the first
field, the last picture's two, and the last picture before a format change. The patch deinterlaces
those spatially and drains before the new format. The `ffmpeg9` build applies it to MPP 1.1.0.
