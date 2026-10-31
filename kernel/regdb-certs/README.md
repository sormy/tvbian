# regdb-certs — keys our kernels trust for the Wi-Fi regulatory database

cfg80211 loads `/lib/firmware/regulatory.db` only with a signature it trusts, and otherwise holds
every radio to the world domain, `country 00`. Debian's `wireless-regdb` makes its own re-signed
copy the default, `regulatory.db-debian`, signed by `CN=benh@debian.org`; the kernel's built-in key
signs only `regulatory.db-upstream`. Every family's fragment trusts the keys in this directory too:
`CFG80211_CERTIFICATION_ONUS` and `CFG80211_EXTRA_REGDB_KEYDIR`, as Debian's own kernels do.

| File                   | Signs                    | Valid to   | SHA-256                  |
| ---------------------- | ------------------------ | ---------- | ------------------------ |
| `benh@debian.org.x509` | Debian's `regulatory.db` | 2120-01-06 | `AD:11:BB:00:…:F0:B9:36` |

Extracted from Debian's signature, on a box with `wireless-regdb` installed:

```sh
openssl pkcs7 -inform DER -in /lib/firmware/regulatory.db.p7s-debian -print_certs | openssl x509 -outform DER > benh@debian.org.x509
```

✅ Byte-identical from `wireless-regdb 2026.05.30-1~deb13u1`, 2026-10-29. A box trusts it when its
boot log has no `regulatory.db is malformed or signature is missing/invalid` and `iw reg set DE`
moves `iw reg get` off `country 00`.
