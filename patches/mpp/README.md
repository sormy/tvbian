# mpp — Rockchip's MPP, linked into a driver that runs on any SoC

`tvb-va-driver` links libmpp in statically and loads on every board. libmpp ran its platform probe
from a constructor as it loaded: every process read the device tree, and off Rockchip each one
logged "can not found match soc name". `0001` makes the probe a call, which the driver makes only
after it finds `/dev/mpp_service`. `va-driver/build.sh` applies it to MPP at the commit it pins.

| Patch  | Fixes                                                | Upstream |
| ------ | ---------------------------------------------------- | -------- |
| `0001` | the platform probe and its log line in every process | not sent |
