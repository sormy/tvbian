# Falkon's QtWebEngine dependency

Falkon master `bf75426ad15f671be3b30b03c2195ba1264d719c` (2026-11-16). Paths are from Falkon's repo
root; counts are `grep` over `src/` (`*.cpp`, `*.h`). "Inference" marks what was not read in full.

## Build

| Item                 | Evidence                                                                                                                                                                    |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Qt minimum           | 6.4.0 (`CMakeLists.txt:14`)                                                                                                                                                 |
| QtWebEngine          | `Qt6WebEngineCore` and `Qt6WebEngineWidgets` required, no option (`CMakeLists.txt:63-64`)                                                                                   |
| QtWebEngineQuick     | not in CMake; needed at run time by `src/lib/data/data/thumbnailer.qml:2`, loaded in `src/lib/tools/pagethumbnailer.cpp:31-36`                                              |
| Library              | `FalkonPrivate` links WebEngineWidgets, WebChannel, PrintSupport, QuickWidgets with no PUBLIC/PRIVATE keyword, so consumers inherit them (`src/lib/CMakeLists.txt:606-616`) |
| Plugins              | every C++ plugin links only `FalkonPrivate`                                                                                                                                 |
| PyFalkon             | PySide typesystems for QtWebEngineCore and QtWebEngineWidgets (`src/plugins/PyFalkon/typesystem_pyfalkon.xml:3-4`)                                                          |
| Version checks       | `QTWEBENGINECORE_VERSION` for 6.6–6.9 in webpage, preferences, mainapplication, networkmanager, siteinfo, sitesettingsmanager                                               |
| Chromium environment | builds `QTWEBENGINE_CHROMIUM_FLAGS` (`src/lib/app/mainapplication.cpp:459-485`)                                                                                             |

## Types used

| Type                                                       |            Files / refs | Used for                                                                                                                                                                                                       |
| ---------------------------------------------------------- | ----------------------: | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `QWebEnginePage`                                           |                44 / 234 | subclassed by `WebPage`; load signals, permissions (`Feature`), fullscreen, certificates, auth, new windows, find, audio, `runJavaScript`, `setWebChannel`, `printToPdf`, `setInspectedPage`, `WebAction` enum |
| `QWebEngineSettings`                                       |                23 / 203 | about 30 attributes, fonts, per-site application (`src/lib/webengine/webpage.cpp:469-505`)                                                                                                                     |
| `QWebEngineScript`, `ScriptCollection`                     |         11 / 67, 7 / 14 | injection points, worlds, sub-frames; autofill, GreaseMonkey, profile scripts                                                                                                                                  |
| `QWebEngineView`                                           |                 15 / 54 | subclassed by `WebView` and `WebInspector`                                                                                                                                                                     |
| `QWebEngineProfile` (+ `ProfileBuilder` ≥ 6.9)             |                 23 / 38 | storage, cache, spell check, languages, interceptor, scheme handlers, cookies, scripts, notifications, downloads                                                                                               |
| `QWebEngineUrlRequestInterceptor`, `UrlRequestInfo`        |          2 / 3, 10 / 42 | AdBlock, Do Not Track, per-domain user agent                                                                                                                                                                   |
| `QWebEngineUrlSchemeHandler`, `UrlRequestJob`, `UrlScheme` | 8 / 12, 14 / 49, 3 / 25 | `falkon:`, `extension:`, `abp-resource:`, KIO schemes                                                                                                                                                          |
| `QWebEngineDownloadRequest`                                |                  8 / 33 | downloads incl. pause/resume and save-page formats                                                                                                                                                             |
| `QWebEngineCertificateError`                               |                  5 / 33 | all 18 error types mapped; public `NetworkManager` API                                                                                                                                                         |
| `QWebEngineHistory`, `HistoryItem`                         |          13 / 25, 2 / 7 | navigation; **whole history serialized through QDataStream into sessions**                                                                                                                                     |
| `QWebEngineNewWindowRequest`                               |                 11 / 20 | new tabs and windows; plugin API                                                                                                                                                                               |
| `QWebEngineContextMenuRequest`                             |                  4 / 11 | spell suggestions, media type, hit test                                                                                                                                                                        |
| `QWebEngineCookieStore`                                    |                   2 / 6 | load all, filter, added/removed, set, delete                                                                                                                                                                   |
| `QWebChannel`                                              |                   4 / 7 | `window.external` bridge in an isolated world                                                                                                                                                                  |
| others                                                     |                   small | `FindTextResult`, `FullScreenRequest`, `RegisterProtocolHandlerRequest`, `ClientCertificateSelection`, `Notification`, `HttpRequest`                                                                           |

Not used: `QWebEngineFileSystemAccessRequest`, `QuotaRequest`, the Qt 6.8 `QWebEnginePermission`,
`ClientHints`, `WebAuthUxRequest`.

## Subclasses

| Falkon class                                                                                        | Base                              | Overrides                                                                                                                                                                                    |
| --------------------------------------------------------------------------------------------------- | --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `WebPage` (`src/lib/webengine/webpage.h:38`)                                                        | `QWebEnginePage`                  | `acceptNavigationRequest`, `chooseFiles`, `javaScriptAlert/Confirm/Prompt/ConsoleMessage`; new windows by signal; nested event loops for synchronous JS and printing (`webpage.cpp:145-175`) |
| `WebView` (`src/lib/webengine/webview.h:33`)                                                        | `QWebEngineView`                  | event filter on QtWebEngine's internal render widget (`webview.cpp:1280-1370`), context menu, resize                                                                                         |
| `TabbedWebView`, `PopupWebView`                                                                     | `WebView`                         | `setPage`, `isFullScreen`                                                                                                                                                                    |
| `WebInspector`                                                                                      | `QWebEngineView`                  | `setInspectedPage`                                                                                                                                                                           |
| `NetworkUrlInterceptor`                                                                             | `QWebEngineUrlRequestInterceptor` | fans out to Falkon's `UrlInterceptor` list                                                                                                                                                   |
| `FalkonSchemeHandler`, `ExtensionSchemeManager`, `AdblockResourceSchemeHandler`, `KIOSchemeHandler` | `QWebEngineUrlSchemeHandler`      | `requestStarted`                                                                                                                                                                             |

## Where the engine is used

120 of 635 source files name a QtWebEngine type; 125 use Falkon's `WebView`/`WebPage` wrappers.

| Subsystem                  | Dependency                                                                                               |
| -------------------------- | -------------------------------------------------------------------------------------------------------- |
| Bootstrap                  | profile, settings, scripts, schemes, Chromium flags (`src/lib/app/mainapplication.cpp`)                  |
| Network                    | scheme handlers, interceptor, certificate policy, Accept-Language (`src/lib/network/networkmanager.cpp`) |
| AdBlock                    | `QWebEngineUrlRequestInfo` throughout; element hiding through `runJavaScript`                            |
| Autofill, passwords        | form observer script in the isolated world; callback over `QWebChannel`                                  |
| GreaseMonkey               | script collection; GM values over `QWebChannel`                                                          |
| Sessions                   | opaque `QWebEngineHistory` blob (`src/lib/webtab/webtab.cpp:373,590`)                                    |
| History, bookmarks         | engine-free databases; favicons from `QWebEngineView::icon`                                              |
| Downloads, cookies         | the engine's request and store types                                                                     |
| Site settings, permissions | keyed by `WebAttribute` and `Feature` (`src/lib/other/sitesettingsmanager.*`)                            |
| PDF, DevTools, printing    | Chromium's viewer, `setInspectedPage`, `print`/`printToPdf`                                              |
| Hit testing, scrollbars    | JavaScript strings from `src/lib/tools/scripts.cpp`; `contentsSize`, `scrollPosition`                    |

## Plugin API

- `PluginInterface` includes `<QWebEnginePage>` and takes `QWebEnginePage::NavigationType` and
  `QWebEngineNewWindowRequest&` (`src/lib/plugins/plugininterface.h:22,65-66`).
- `WebView`, `WebPage`, `mApp->webProfile()`, `UrlInterceptor`, `ExtensionSchemeHandler`,
  `NetworkManager::certificateError` and `WebTab::history()` expose QtWebEngine types to plugins.
- The QML plugin API wraps the types but mirrors their semantics; PyFalkon exposes them raw.
- Plugins using QtWebEngine directly: GreaseMonkey, KDEFrameworksIntegration, StatusBarIcons,
  SiteSettingsView, PIM, TabManager, MouseGestures, VerticalTabs, PyFalkon.

## `falkon:` pages and bridges

- `FalkonSchemeHandler` serves `about`, `start`, `speeddial`, `config`, `restore` from qrc
  templates; the schemes are registered secure and CSP-exempt
  (`src/lib/network/networkmanager.cpp:389-407`).
- One `QWebChannel` per page in the isolated world (`src/lib/webengine/webpage.cpp:88-90`);
  `Scripts::setupWebChannel()` injects `qwebchannel.js` and builds `window.external` for all frames
  (`src/lib/tools/scripts.cpp:26-71`). C++ objects reached: SpeedDial, RecoveryJsObject,
  AutoFillJsObject, GreaseMonkey's object.
- A port needs a `qt.webChannelTransport`-compatible transport in an isolated world, per-world user
  scripts in sub-frames, and secure custom schemes with reply and redirect (inference).

## Size

| Metric                            | Value                  |
| --------------------------------- | ---------------------- |
| C++ in `src/`                     | 89,513 LOC             |
| In files naming QtWebEngine types | 29,133 LOC, 120 files  |
| Lines naming QtWebEngine types    | 743, plus 128 includes |
| `src/lib/webengine/`              | 3,838 LOC              |

Most coupled: `src/lib/other/sitesettingsmanager.cpp`, `src/lib/app/mainapplication.cpp`,
`src/lib/webengine/webview.cpp`, `src/lib/webengine/webpage.cpp`,
`src/lib/network/networkmanager.cpp`, `src/lib/adblock/adblockrule.cpp`.

## History

No multi-backend support ever: QupZilla replaced QtWebKit with QtWebEngine in place (`60b2386a`,
2015-01-27, 107 files). The only leftover is a dead `#ifdef QTWEBENGINE_DISABLED`
(`src/lib/cookies/cookiejar.cpp:217`).
