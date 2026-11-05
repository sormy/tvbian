# Website

One HTML page, built on the host with Python's standard library:

```sh
python3 site/build.py
```

Writes `build/out/site/index.html`, `media/` and `CNAME`. The domain is `tvbian.com`.

## Discovery

| Data                        | Source                        |
| --------------------------- | ----------------------------- |
| Listed boards, order, specs | `README.md` box table         |
| Identity, family, hostname  | `boards/<board>/board.conf`   |
| Product and store links     | `BOARD_HOME`, `BOARD_STORE`   |
| Install guide               | Box table's install link      |
| Product photo               | `docs/<board>/image1.*`       |
| Image download              | Release assets                |
| Previous board ID           | `BOARD_RENAMED_FROM`          |
| Family filters              | Listed boards' families       |
| GitHub stars                | Repository API, at build time |

The table's board link joins its row to `boards/<board>/board.conf`. Unlisted board directories are
not advertised. A listed board must have a matching ID, a board report and an install guide. Photos
use the first existing `image1.jpg`, `.png`, `.jpeg` or `.webp`.

Downloads match `tvbian-<board>-<suite>-<date>.img.xz`; variants are excluded. A renamed board falls
back to its previous ID when the release predates the rename. Multiple matching images are an error.
A missing board download is labelled; a release with no downloads for listed boards fails before
writing the page.

`--tag` selects an image release; absent, the latest non-prerelease is used. `--release-json` reads
a saved GitHub API response offline and omits the star count. `GH_TOKEN`, or `GITHUB_TOKEN`,
authenticates API requests when set. An unavailable star count omits its badge.

## Publishing

| Trigger                                | Result                          |
| -------------------------------------- | ------------------------------- |
| An image release published by CI       | Pages, that release             |
| A push to `main` changing a site input | Pages, the latest image release |
| A pull request changing a site input   | Tests and build; no deploy      |
| A manual dispatch                      | Pages, an optional image tag    |

`release/publish.sh` sets the `tag` output once the images are up; an apt-only run sets none. The
release workflow then calls `.github/workflows/pages.yml` with it: a release made with
`GITHUB_TOKEN` starts no other workflow.

Every build runs the site tests on the commit that started it: the release's built commit, `main`,
or a pull request's merge ref. A newer build of a pull request cancels the older; a production
deploy is never cancelled. Only the deploy job gets Pages write and OIDC; no publishing secret.

Hosting requires the repository's Pages source set to **GitHub Actions**, the custom domain
`tvbian.com`, and DNS pointing to GitHub Pages.

## Page behaviour

Family filters and theme selection use browser JavaScript. The theme follows the system until
chosen, then stays in browser storage. Without JavaScript, all boards remain visible. Section links
set the URL anchor; scrolling leaves it unchanged for browser scroll restoration.

The terminal preview uses the first listed board, its selected image's Debian codename, and the
ASCII logo from `base/motd`. Color roles follow the banner's ANSI codes; addresses and statistics
are illustrative.

`site/coffee.url` is one `https` URL on its own line. When present, the footer displays it.

Questions, bugs and test results go to GitHub Issues; patches go to pull requests. Email uses
`admin@tvbian.com` for hardware donations and `sales@tvbian.com` for sponsorship and commercial
enquiries. The footer states independence from Debian and credits the Debian trademark.
