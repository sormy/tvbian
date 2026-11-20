# Request interception

WebKit asks the UI process nothing per request. QtWpeWebKit gets requests two ways.

## `QWebEngineUrlRequestInterceptor`: every request, answered synchronously

A web-process extension (`webprocess/requests.cpp`, built as
`lib/qtwpewebkit/web-process-extensions/libqtwpewebkit-requests.so` next to `libqtwpewebkit`)
handles `WebKitWebPage::send-request` for every request of every page, including redirects and the
page's own document. It sends the request to the UI process over a local socket and waits for the
answer: block, redirect URL, headers to set. `compat/src/requestinterception.cpp` answers by running
the profile's interceptor and then the page's, as QtWebEngine does.

- Waiting keeps QtWebEngine's semantics exact: an interceptor decides before the request leaves,
  with any C++ logic. The rule-set alternative (the UI process pushes data, the extension applies
  it) needs a QtWpeWebKit-specific API per kind of decision, and an existing interceptor would never
  run.
- Interceptors run on a QtWpeWebKit thread, as QtWebEngine 5 ran them on its IO thread. On the
  Mali-450 box the UI thread was busy enough to keep each request waiting 6–9 ms. On a separate
  thread the wait is the interceptor's own time.
- The socket lives in a private directory that is mounted into WebKit's bubblewrap sandbox, which
  has its own `/tmp`.

## Adblock Plus filter lists: WebKit content blockers

`QWebEngineProfile::setAdblockFilters(lists)` is a QtWpeWebKit extension. It converts the filters
into WebKit's content-blocker JSON (`compat/src/adblockfilters.cpp`), and WebKit compiles that into
a DFA that it matches inside the web process. The compiled list is cached by content hash under
`$XDG_CACHE_HOME/<app>/qtwpewebkit-content-filters` (`compat/src/contentfilter.cpp`).

- Speed. Falkon's own matcher scans EasyList's 48,000 `||domain^` rules linearly, which took about
  20 ms per request on the box. WebKit's DFA takes microseconds.
- Cost. EasyList, NoCoin and custom rules make 76,000 WebKit rules. Converting them takes about 7 s
  on a background thread, and WebKit compiles them in about 35 s in the background, once per change
  to the lists. After that, a cached copy loads in about 1 ms. Until the first compilation finishes,
  pages load unfiltered.
- What gets dropped: regular-expression filters (`/…/`), `$redirect`, `$rewrite`, `$csp`,
  `$removeparam` and other options outside a content blocker's reach, extended selectors (`#?#`),
  scriptlets (`#$#`, `##+js`), entity domains (`example.*`) and non-ASCII patterns. Element-hiding
  exceptions (`#@#`), `$document`, `$elemhide` and `$generichide` are kept only when they name
  domains. `domain=` matches the top document, not the frame, and third-party means a different
  registrable domain than the top document. A trailing `^` needs a following character.

## How this differs from QtWebEngine

- `interceptRequest()` runs off the UI thread, so it must be thread-safe.
- `resourceType()` comes from `Sec-Fetch-Dest`, which WebKit sends only to secure origins, including
  localhost. Otherwise it comes from the `Accept` header, which tells documents, images and style
  sheets apart; everything else is `ResourceTypeUnknown`. A frame whose URL is the page's own counts
  as the main frame.
- `navigationType()` is the latest navigation's type for frames, and `NavigationTypeOther` for
  everything else. `initiator()` is empty.
- WebKit loads an empty page in place of a blocked page; QtWpeWebKit reports the load as failed, as
  QtWebEngine does.
- `data:` URLs are not intercepted. Nothing outside a page is intercepted: downloads started by the
  application, service workers' own fetches, and the network process's speculative loads. WebKit's
  network cache replays the subresources it recorded on an earlier visit (on by default in GLib
  ports, with no API to turn it off). The replay repeats the requests as they were intercepted then,
  so a newly blocked URL can still be fetched once, on the first visit after the change.
- WebKit reports no blocked load, so no one gets a per-request notice of what a content blocker
  blocked.
