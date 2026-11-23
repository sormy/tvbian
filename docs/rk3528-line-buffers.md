# RK3528 display line buffers

The RK3528 splits one line buffer between its Esmart display planes. The split decides which Esmart
planes exist and how wide each can be; Cluster0, the 4K video plane, is outside it. Every board's
tree sets `02`, the split tested here; the kernel command line overrides it.

| Value | Esmart buffers      | HDMI's Esmart planes        | Composite's planes |
| ----- | ------------------- | --------------------------- | ------------------ |
| `02`  | 0: 4K, 2: 2K, 3: 2K | desktop 4K, cursor          | Esmart3, Esmart2   |
| `01`  | 0: 4K, 2: 4K        | desktop 4K, cursor 4K       | Esmart2            |
| `03`  | 0–3: 2K each        | desktop 2K, overlay, cursor | Esmart3, Esmart2   |
| `00`  | 0: 8K               | desktop 8K                  | none               |

Esmart2 serves HDMI and composite both; a desktop wider than 2048 needs `00`, `01` or `02`.

To change it, on the box, then reboot:

```sh
P='rockchipdrm.esmart_lb_mode=1'
F=/etc/u-boot-menu/conf.d/zz-esmart.conf
echo "U_BOOT_PARAMETERS=\"\$U_BOOT_PARAMETERS $P\"" | sudo tee $F
sudo u-boot-update
```

To go back to the tree's value, remove that file and run `sudo u-boot-update`.
