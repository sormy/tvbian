// A page's content and presentation: setHtml/toHtml, find, zoom, user agent and settings
#include "webtest.h"

#include <QWebEngineFindTextResult>
#include <QWebEngineProfile>
#include <QWebEngineSettings>

using Settings = QWebEngineSettings;

class tst_Content : public QObject {
    Q_OBJECT

private Q_SLOTS:
    void init() { m_server = std::make_unique<TestServer>(); }
    void cleanup() { m_server.reset(); }

    void setHtmlToHtml()
    {
        ShownView shown;
        QWebEnginePage* page = shown.page();
        QVERIFY(setsHtml(page, QStringLiteral("<html><head><title>Тест</title></head><body><p id=\"p\">héllo ✓</p></body></html>")));
        QCOMPARE(page->title(), QStringLiteral("Тест"));
        std::optional<QString> html;
        page->toHtml([&html](const QString& result) { html = result; });
        QTRY_VERIFY(html.has_value());
        QVERIFY2(html->startsWith(QStringLiteral("<html><head><title>Тест</title></head>")), qPrintable(*html));
        QVERIFY2(html->contains(QStringLiteral("<p id=\"p\">héllo ✓</p>")), qPrintable(*html));
        std::optional<QString> text;
        page->toPlainText([&text](const QString& result) { text = result; });
        QTRY_VERIFY(text.has_value());
        QCOMPARE(text->trimmed(), QStringLiteral("héllo ✓"));
    }

    void setHtmlUrl_data()
    {
        QTest::addColumn<bool>("withBaseUrl");
        QTest::newRow("no base URL") << false;
        QTest::newRow("base URL") << true;
    }

    void setHtmlUrl()
    {
        QFETCH(bool, withBaseUrl);
        m_server->route("/dot.png", HttpReply { QByteArray::fromBase64("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="), "image/png" });
        ShownView shown;
        const QUrl baseUrl = withBaseUrl ? m_server->url("/dir/") : QUrl();
        QVERIFY(setsHtml(shown.page(), QStringLiteral("<img src=\"/dot.png\">"), baseUrl));
        if (withBaseUrl)
            QCOMPARE(shown.page()->url(), baseUrl);
        else
            QCOMPARE(shown.page()->url().scheme(), QStringLiteral("data"));
        QTest::qWait(200);
        QCOMPARE(m_server->requestCount("/dot.png"), withBaseUrl ? 1 : 0);
    }

    void setContent_data()
    {
        QTest::addColumn<QByteArray>("data");
        QTest::addColumn<QString>("mimeType");
        QTest::addColumn<QString>("text");
        QTest::newRow("plain text") << QByteArray("<b>not bold</b>") << QStringLiteral("text/plain") << QStringLiteral("<b>not bold</b>");
        QTest::newRow("html") << QByteArray("<b>bold</b>") << QStringLiteral("text/html") << QStringLiteral("bold");
        QTest::newRow("utf-8 charset") << QByteArray("<p>ж</p>") << QStringLiteral("text/html;charset=utf-8") << QStringLiteral("ж");
    }

    void setContent()
    {
        QFETCH(QByteArray, data);
        QFETCH(QString, mimeType);
        QFETCH(QString, text);
        ShownView shown;
        QVERIFY(loadsOk(shown.page(), [&] { shown.page()->setContent(data, mimeType); }));
        QCOMPARE(evaluate(shown.page(), QStringLiteral("document.body.innerText")).toString().trimmed(), text);
    }

    void findText_data()
    {
        QTest::addColumn<QStringList>("searches");
        QTest::addColumn<int>("flags");
        QTest::addColumn<int>("matches");
        QTest::addColumn<int>("activeMatch");
        const QStringList foo { QStringLiteral("foo") };
        QTest::newRow("case-insensitive") << foo << 0 << 3 << 1;
        QTest::newRow("case-sensitive") << foo << int(QWebEnginePage::FindCaseSensitively) << 2 << 1;
        QTest::newRow("missing") << QStringList { QStringLiteral("missing") } << 0 << 0 << 0;
        QTest::newRow("non-ASCII") << QStringList { QStringLiteral("жук") } << 0 << 1 << 1;
        QTest::newRow("next") << QStringList { foo.first(), foo.first() } << 0 << 3 << 2;
        QTest::newRow("backward from start") << foo << int(QWebEnginePage::FindBackward) << 3 << 3;
        QTest::newRow("cleared") << QStringList { foo.first(), QString() } << 0 << 0 << 0;
    }

    void findText()
    {
        QFETCH(QStringList, searches);
        QFETCH(int, flags);
        QFETCH(int, matches);
        QFETCH(int, activeMatch);
        ShownView shown;
        QWebEnginePage* page = shown.page();
        QVERIFY(setsHtml(page, QStringLiteral("<p>foo bar foo</p><p>FOO жук</p>")));
        QSignalSpy finished(page, &QWebEnginePage::findTextFinished);
        std::optional<QWebEngineFindTextResult> result;
        for (const QString& search : searches) {
            result.reset();
            page->findText(search, QWebEnginePage::FindFlags(flags), [&result](const QWebEngineFindTextResult& found) { result = found; });
            QTRY_VERIFY(result.has_value());
        }
        QCOMPARE(result->numberOfMatches(), matches);
        QCOMPARE(result->activeMatch(), activeMatch);
        QTRY_COMPARE(finished.count(), searches.size());
        const auto signalled = finished.last().first().value<QWebEngineFindTextResult>();
        QCOMPARE(signalled.numberOfMatches(), matches);
    }

    void zoom_data()
    {
        QTest::addColumn<qreal>("factor");
        QTest::addColumn<qreal>("expected");
        QTest::newRow("2") << 2.0 << 2.0;
        QTest::newRow("0.5") << 0.5 << 0.5;
        QTest::newRow("too large") << 10.0 << 1.0;
        QTest::newRow("too small") << 0.1 << 1.0;
    }

    void zoom()
    {
        QFETCH(qreal, factor);
        QFETCH(qreal, expected);
        ShownView shown;
        QWebEnginePage* page = shown.page();
        QVERIFY(setsHtml(page, QStringLiteral("<p>zoom</p>")));
        QCOMPARE(page->zoomFactor(), 1.0);
        const int width = evaluate(page, QStringLiteral("innerWidth")).toInt();
        QVERIFY(width > 0);
        page->setZoomFactor(factor);
        QCOMPARE(page->zoomFactor(), expected);
        QTRY_COMPARE(evaluate(page, QStringLiteral("innerWidth")).toInt(), qRound(width / expected));
    }

    void userAgent()
    {
        QWebEngineProfile profile;
        QVERIFY(!profile.httpUserAgent().isEmpty());
        const QString agent = QStringLiteral("QtWpeWebKitTest/1.0 (like nothing)");
        profile.setHttpUserAgent(agent);
        QCOMPARE(profile.httpUserAgent(), agent);
        m_server->route("/page", "<p>ua</p>");
        ShownView shown(new QWebEnginePage(&profile));
        QVERIFY(loadsOk(shown.page(), m_server->url("/page")));
        QCOMPARE(m_server->requestHeader("/page", "User-Agent"), agent.toUtf8());
        QCOMPARE(evaluate(shown.page(), QStringLiteral("navigator.userAgent")), QVariant(agent));
    }

    void defaultAttributes_data()
    {
        QTest::addColumn<int>("attribute");
        QTest::addColumn<bool>("on");
        const struct {
            Settings::WebAttribute attribute;
            const char* name;
            bool on;
        } defaults[] = {
            { Settings::AutoLoadImages, "AutoLoadImages", true },
            { Settings::JavascriptEnabled, "JavascriptEnabled", true },
            { Settings::JavascriptCanOpenWindows, "JavascriptCanOpenWindows", true },
            { Settings::JavascriptCanAccessClipboard, "JavascriptCanAccessClipboard", false },
            { Settings::LinksIncludedInFocusChain, "LinksIncludedInFocusChain", true },
            { Settings::LocalStorageEnabled, "LocalStorageEnabled", true },
            { Settings::LocalContentCanAccessRemoteUrls, "LocalContentCanAccessRemoteUrls", false },
            { Settings::XSSAuditingEnabled, "XSSAuditingEnabled", false },
            { Settings::SpatialNavigationEnabled, "SpatialNavigationEnabled", false },
            { Settings::LocalContentCanAccessFileUrls, "LocalContentCanAccessFileUrls", true },
            { Settings::HyperlinkAuditingEnabled, "HyperlinkAuditingEnabled", false },
            { Settings::ScrollAnimatorEnabled, "ScrollAnimatorEnabled", false },
            { Settings::ErrorPageEnabled, "ErrorPageEnabled", true },
            { Settings::PluginsEnabled, "PluginsEnabled", false },
            { Settings::FullScreenSupportEnabled, "FullScreenSupportEnabled", false },
            { Settings::ScreenCaptureEnabled, "ScreenCaptureEnabled", false },
            { Settings::WebGLEnabled, "WebGLEnabled", true },
            { Settings::Accelerated2dCanvasEnabled, "Accelerated2dCanvasEnabled", true },
            { Settings::AutoLoadIconsForPage, "AutoLoadIconsForPage", true },
            { Settings::TouchIconsEnabled, "TouchIconsEnabled", false },
            { Settings::FocusOnNavigationEnabled, "FocusOnNavigationEnabled", false },
            { Settings::PrintElementBackgrounds, "PrintElementBackgrounds", true },
            { Settings::AllowRunningInsecureContent, "AllowRunningInsecureContent", false },
            { Settings::AllowGeolocationOnInsecureOrigins, "AllowGeolocationOnInsecureOrigins", false },
            { Settings::AllowWindowActivationFromJavaScript, "AllowWindowActivationFromJavaScript", false },
            { Settings::ShowScrollBars, "ShowScrollBars", true },
            { Settings::PlaybackRequiresUserGesture, "PlaybackRequiresUserGesture", false },
            { Settings::WebRTCPublicInterfacesOnly, "WebRTCPublicInterfacesOnly", false },
            { Settings::JavascriptCanPaste, "JavascriptCanPaste", false },
            { Settings::DnsPrefetchEnabled, "DnsPrefetchEnabled", false },
            { Settings::PdfViewerEnabled, "PdfViewerEnabled", true },
            { Settings::NavigateOnDropEnabled, "NavigateOnDropEnabled", true },
            { Settings::ReadingFromCanvasEnabled, "ReadingFromCanvasEnabled", true },
            { Settings::ForceDarkMode, "ForceDarkMode", false },
        };
        for (const auto& [attribute, name, on] : defaults)
            QTest::newRow(name) << int(attribute) << on;
    }

    void defaultAttributes()
    {
        QFETCH(int, attribute);
        QFETCH(bool, on);
        ShownView shown;
        QCOMPARE(shown.page()->settings()->testAttribute(Settings::WebAttribute(attribute)), on);
        QCOMPARE(shown.page()->profile()->settings()->testAttribute(Settings::WebAttribute(attribute)), on);
    }

    // A page's settings follow the profile's until set on the page
    void settingsInheritance()
    {
        QWebEngineProfile profile;
        ShownView shown(new QWebEnginePage(&profile));
        Settings* pageSettings = shown.page()->settings();
        profile.settings()->setAttribute(Settings::AutoLoadImages, false);
        QVERIFY(!pageSettings->testAttribute(Settings::AutoLoadImages));
        pageSettings->setAttribute(Settings::AutoLoadImages, true);
        profile.settings()->setAttribute(Settings::AutoLoadImages, false);
        QVERIFY(pageSettings->testAttribute(Settings::AutoLoadImages));
        pageSettings->resetAttribute(Settings::AutoLoadImages);
        QVERIFY(!pageSettings->testAttribute(Settings::AutoLoadImages));
    }

    void autoLoadImages_data()
    {
        QTest::addColumn<bool>("on");
        QTest::newRow("on") << true;
        QTest::newRow("off") << false;
    }

    void autoLoadImages()
    {
        QFETCH(bool, on);
        m_server->route("/dot.png", HttpReply { QByteArray::fromBase64("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="), "image/png" });
        m_server->route("/page", "<img id=img src=/dot.png>");
        ShownView shown;
        shown.page()->settings()->setAttribute(Settings::AutoLoadImages, on);
        QVERIFY(loadsOk(shown.page(), m_server->url("/page")));
        QTest::qWait(300);
        QCOMPARE(m_server->requestCount("/dot.png"), on ? 1 : 0);
        QCOMPARE(evaluate(shown.page(), QStringLiteral("document.getElementById('img').naturalWidth")).toInt(), on ? 1 : 0);
    }

    void fontSizes_data()
    {
        QTest::addColumn<int>("which");
        QTest::addColumn<int>("defaultSize");
        QTest::addColumn<QString>("element");
        QTest::newRow("default") << int(Settings::DefaultFontSize) << 16 << QStringLiteral("p");
        QTest::newRow("default fixed") << int(Settings::DefaultFixedFontSize) << 13 << QStringLiteral("code");
    }

    void fontSizes()
    {
        QFETCH(int, which);
        QFETCH(int, defaultSize);
        QFETCH(QString, element);
        ShownView shown;
        Settings* settings = shown.page()->settings();
        const auto size = Settings::FontSize(which);
        QCOMPARE(settings->fontSize(size), defaultSize);
        settings->setFontSize(size, 23);
        QCOMPARE(settings->fontSize(size), 23);
        QVERIFY(setsHtml(shown.page(), QStringLiteral("<p>text <code>code</code></p>")));
        QCOMPARE(evaluate(shown.page(), QStringLiteral("getComputedStyle(document.querySelector('%1')).fontSize").arg(element)),
            QVariant(QStringLiteral("23px")));
        settings->resetFontSize(size);
        QCOMPARE(settings->fontSize(size), defaultSize);
    }

    void minimumFontSize()
    {
        ShownView shown;
        shown.page()->settings()->setFontSize(Settings::MinimumFontSize, 20);
        QVERIFY(setsHtml(shown.page(), QStringLiteral("<span id=s style=\"font-size: 5px\">tiny</span>")));
        QCOMPARE(evaluate(shown.page(), QStringLiteral("getComputedStyle(document.getElementById('s')).fontSize")),
            QVariant(QStringLiteral("20px")));
    }

    void fontFamilies()
    {
        ShownView shown;
        Settings* settings = shown.page()->settings();
        const QString original = settings->fontFamily(Settings::FixedFont);
        QVERIFY(!original.isEmpty());
        settings->setFontFamily(Settings::FixedFont, QStringLiteral("QtWpeWebKit Test Mono"));
        QCOMPARE(settings->fontFamily(Settings::FixedFont), QStringLiteral("QtWpeWebKit Test Mono"));
        settings->resetFontFamily(Settings::FixedFont);
        QCOMPARE(settings->fontFamily(Settings::FixedFont), original);
    }

    void defaultTextEncoding()
    {
        m_server->route("/latin1", HttpReply { "<p>caf\xe9</p>", "text/html" });
        ShownView shown;
        shown.page()->settings()->setDefaultTextEncoding(QStringLiteral("ISO-8859-1"));
        QCOMPARE(shown.page()->settings()->defaultTextEncoding(), QStringLiteral("ISO-8859-1"));
        QVERIFY(loadsOk(shown.page(), m_server->url("/latin1")));
        QCOMPARE(evaluate(shown.page(), QStringLiteral("document.body.innerText")).toString().trimmed(), QStringLiteral("café"));
    }

    // The APIs a call and a streaming site use are there, as in Chromium, with no setting to turn on
    void webApis_data()
    {
        QTest::addColumn<QString>("api");
        QTest::newRow("RTCPeerConnection") << QStringLiteral("RTCPeerConnection");
        QTest::newRow("getUserMedia") << QStringLiteral("navigator.mediaDevices && navigator.mediaDevices.getUserMedia");
        QTest::newRow("MediaSource") << QStringLiteral("MediaSource");
    }

    void webApis()
    {
        QFETCH(QString, api);
        m_server->route("/apis", "<p>apis");
        ShownView shown;
        QVERIFY(loadsOk(shown.page(), m_server->url("/apis")));
        QCOMPARE(evaluate(shown.page(), QStringLiteral("typeof (%1)").arg(api)).toString(), QStringLiteral("function"));
    }

private:
    std::unique_ptr<TestServer> m_server;
};

QTEST_MAIN(tst_Content)
#include "tst_content.moc"
