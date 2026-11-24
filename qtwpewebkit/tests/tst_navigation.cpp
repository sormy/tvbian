// Loading, navigation signals, session history, navigation requests and new windows
#include "webtest.h"

#include <QBuffer>
#include <QDataStream>
#include <QWebEngineFullScreenRequest>
#include <QWebEngineHistory>
#include <QWebEngineNewWindowRequest>
#include <QWebEngineProfile>
#include <QWebEngineSettings>

static QByteArray titled(const QByteArray& title, const QByteArray& body = {})
{
    return "<html><head><title>" + title + "</title></head><body>" + body + "</body></html>";
}

// A URL nothing listens on
// Time a page takes to draw: Chromium drops input before its first frame
static const int firstFrameMs = 1500;

// A user's click on the page, once it can take one, confirmed by the page
static bool clickPage(ShownView& shown)
{
    evaluate(shown.page(), QStringLiteral("addEventListener('click', () => window.clicked = true)"));
    shown.view.setFocus();
    QTest::qWait(firstFrameMs);
    QTest::mouseClick(shown.view.focusProxy(), Qt::LeftButton, {}, QPoint(100, 100));
    return QTest::qWaitFor([&] { return evaluate(shown.page(), QStringLiteral("window.clicked === true")).toBool(); });
}

static QUrl refusedUrl()
{
    QTcpServer closed;
    closed.listen(QHostAddress::LocalHost);
    return QUrl(QStringLiteral("http://127.0.0.1:%1/").arg(closed.serverPort()));
}

// Records the navigation requests it sees and refuses those to a path containing "blocked"
class RecordingPage : public QWebEnginePage {
public:
    using QWebEnginePage::QWebEnginePage;
    struct Request {
        QUrl url;
        NavigationType type;
        bool isMainFrame;
    };
    QList<Request> requests;

protected:
    bool acceptNavigationRequest(const QUrl& url, NavigationType type, bool isMainFrame) override
    {
        requests.append({ url, type, isMainFrame });
        return !url.path().contains(QLatin1String("blocked"));
    }
};

class tst_Navigation : public QObject {
    Q_OBJECT

private Q_SLOTS:
    void init()
    {
        m_server = std::make_unique<TestServer>();
        for (const QByteArray& name : { "a", "b", "c" })
            m_server->route("/" + name, titled(name));
    }
    void cleanup() { m_server.reset(); }

    void loadSignals()
    {
        ShownView shown;
        QWebEnginePage* page = shown.page();
        QSignalSpy started(page, &QWebEnginePage::loadStarted);
        QSignalSpy progress(page, &QWebEnginePage::loadProgress);
        QSignalSpy urlChanged(page, &QWebEnginePage::urlChanged);
        QSignalSpy titleChanged(page, &QWebEnginePage::titleChanged);
        QSignalSpy finished(page, &QWebEnginePage::loadFinished);
        const QUrl url = m_server->url("/a");

        page->load(url);
        QVERIFY(finished.wait(asyncTimeout));
        QCOMPARE(started.count(), 1);
        QCOMPARE(finished.count(), 1);
        QCOMPARE(finished.first().first().toBool(), true);
        QVERIFY(!progress.isEmpty());
        QCOMPARE(progress.last().first().toInt(), 100);
        QVERIFY(!urlChanged.isEmpty());
        QCOMPARE(urlChanged.last().first().toUrl(), url);
        QTRY_VERIFY(!titleChanged.isEmpty());
        QCOMPARE(titleChanged.last().first().toString(), QStringLiteral("a"));
        QCOMPARE(page->url(), url);
        QCOMPARE(page->requestedUrl(), url);
        QCOMPARE(page->title(), QStringLiteral("a"));
        QVERIFY(!page->isLoading());
    }

    void loadResult_data()
    {
        QTest::addColumn<QByteArray>("path");
        QTest::addColumn<HttpReply>("reply");
        QTest::addColumn<bool>("ok");
        QTest::newRow("200") << QByteArray("/page") << HttpReply { titled("fine") } << true;
        QTest::newRow("404 with body") << QByteArray("/missing") << HttpReply { titled("gone"), "text/html", 404 } << false;
        QTest::newRow("500 with body") << QByteArray("/broken") << HttpReply { titled("oops"), "text/html", 500 } << false;
        QTest::newRow("plain text") << QByteArray("/text") << HttpReply { "just text", "text/plain" } << true;
    }

    void loadResult()
    {
        QFETCH(QByteArray, path);
        QFETCH(HttpReply, reply);
        QFETCH(bool, ok);
        m_server->route(path, reply);
        ShownView shown;
        QCOMPARE(loadsOk(shown.page(), m_server->url(path)), ok);
        QCOMPARE(shown.page()->url(), m_server->url(path));
    }

    void loadFailure()
    {
        ShownView shown;
        QWebEnginePage* page = shown.page();
        QSignalSpy started(page, &QWebEnginePage::loadStarted);
        QSignalSpy finished(page, &QWebEnginePage::loadFinished);
        const QUrl url = refusedUrl();
        QCOMPARE(loadsOk(page, url), false);
        QTest::qWait(300);
        QCOMPARE(started.count(), 1);
        QCOMPARE(finished.count(), 1);
        QCOMPARE(page->requestedUrl(), url);
        QCOMPARE(page->url(), url);
    }

    void untitledPage()
    {
        m_server->route("/untitled", "<p>no title</p>");
        ShownView shown;
        QVERIFY(loadsOk(shown.page(), m_server->url("/untitled")));
        const QUrl url = m_server->url("/untitled");
        QCOMPARE(shown.page()->title(), url.toString(QUrl::RemoveScheme | QUrl::RemoveUserInfo).mid(2));
    }

    void titleChangedByScript()
    {
        ShownView shown;
        QWebEnginePage* page = shown.page();
        QVERIFY(loadsOk(page, m_server->url("/a")));
        QSignalSpy titleChanged(page, &QWebEnginePage::titleChanged);
        evaluate(page, QStringLiteral("document.title = 'ünïcode ✓'"));
        QTRY_VERIFY(!titleChanged.isEmpty());
        QTest::qWait(200);
        QStringList titles;
        for (const QList<QVariant>& emitted : titleChanged)
            titles.append(emitted.first().toString());
        QCOMPARE(titles.join(QLatin1String(" | ")), QStringLiteral("ünïcode ✓"));
        QCOMPARE(page->title(), QStringLiteral("ünïcode ✓"));
    }

    // a browser closes a tab only once its page agrees
    void requestClose()
    {
        ShownView shown;
        QWebEnginePage* page = shown.page();
        QVERIFY(loadsOk(page, m_server->url("/a")));
        QSignalSpy closeRequested(page, &QWebEnginePage::windowCloseRequested);
        page->triggerAction(QWebEnginePage::RequestClose);
        QTRY_COMPARE(closeRequested.count(), 1);
    }

    void sameDocumentNavigation_data()
    {
        QTest::addColumn<QString>("script");
        QTest::addColumn<QString>("expected");
        QTest::newRow("fragment") << QStringLiteral("location.hash = 'part'") << QStringLiteral("/a#part");
        QTest::newRow("pushState") << QStringLiteral("history.pushState({}, '', '/pushed')") << QStringLiteral("/pushed");
        QTest::newRow("replaceState") << QStringLiteral("history.replaceState({}, '', '/replaced')") << QStringLiteral("/replaced");
    }

    void sameDocumentNavigation()
    {
        QFETCH(QString, script);
        QFETCH(QString, expected);
        ShownView shown;
        QWebEnginePage* page = shown.page();
        QVERIFY(loadsOk(page, m_server->url("/a")));
        QSignalSpy started(page, &QWebEnginePage::loadStarted);
        QSignalSpy urlChanged(page, &QWebEnginePage::urlChanged);
        evaluate(page, script);
        const QUrl url = m_server->url(expected.toLatin1());
        QTRY_COMPARE(page->url(), url);
        QCOMPARE(urlChanged.count(), 1);
        QCOMPARE(urlChanged.first().first().toUrl(), url);
        QCOMPARE(started.count(), 0);
        QCOMPARE(m_server->requestCount(expected.toLatin1()), 0);
    }

    void backForward()
    {
        ShownView shown;
        QWebEnginePage* page = shown.page();
        QWebEngineHistory* history = page->history();
        QVERIFY(!history->canGoBack());
        QVERIFY(!history->canGoForward());
        for (const char* name : { "/a", "/b", "/c" })
            QVERIFY(loadsOk(page, m_server->url(name)));

        QCOMPARE(history->count(), 3);
        QCOMPARE(history->currentItemIndex(), 2);
        QVERIFY(history->canGoBack());
        QVERIFY(!history->canGoForward());
        QCOMPARE(history->currentItem().url(), m_server->url("/c"));
        QCOMPARE(history->backItem().title(), QStringLiteral("b"));
        QVERIFY(!history->forwardItem().isValid());

        QVERIFY(loadsOk(page, [&] { history->back(); }));
        QCOMPARE(page->url(), m_server->url("/b"));
        QCOMPARE(history->currentItemIndex(), 1);
        QVERIFY(history->canGoForward());
        QCOMPARE(history->backItems(5).size(), 1);
        QCOMPARE(history->backItems(5).first().url(), m_server->url("/a"));
        QCOMPARE(history->forwardItems(5).size(), 1);
        QCOMPARE(history->forwardItems(5).first().url(), m_server->url("/c"));

        QVERIFY(loadsOk(page, [&] { history->goToItem(history->itemAt(0)); }));
        QCOMPARE(page->url(), m_server->url("/a"));
        QVERIFY(!history->canGoBack());

        QVERIFY(loadsOk(page, [&] { page->triggerAction(QWebEnginePage::Forward); }));
        QCOMPARE(page->url(), m_server->url("/b"));
        QCOMPARE(history->count(), 3);
    }

    void historyEdges()
    {
        ShownView shown;
        QWebEnginePage* page = shown.page();
        QVERIFY(loadsOk(page, m_server->url("/a")));
        QWebEngineHistory* history = page->history();
        QSignalSpy started(page, &QWebEnginePage::loadStarted);
        history->back();
        history->forward();
        QTest::qWait(300);
        QCOMPARE(started.count(), 0);
        QVERIFY(!history->itemAt(5).isValid());
        QVERIFY(!history->itemAt(-1).isValid());
        QCOMPARE(history->items().size(), 1);
        QCOMPARE(history->itemAt(0).title(), QStringLiteral("a"));

        // Loading from the middle of history drops the forward items
        QVERIFY(loadsOk(page, m_server->url("/b")));
        QVERIFY(loadsOk(page, [&] { history->back(); }));
        QVERIFY(loadsOk(page, m_server->url("/c")));
        QCOMPARE(history->count(), 2);
        QVERIFY(!history->canGoForward());
    }

    void reload()
    {
        ShownView shown;
        QWebEnginePage* page = shown.page();
        QVERIFY(loadsOk(page, m_server->url("/a")));
        QVERIFY(loadsOk(page, [&] { page->triggerAction(QWebEnginePage::Reload); }));
        QCOMPARE(m_server->requestCount("/a"), 2);
        QVERIFY(loadsOk(page, [&] { page->triggerAction(QWebEnginePage::ReloadAndBypassCache); }));
        QCOMPARE(m_server->requestCount("/a"), 3);
        QCOMPARE(page->history()->count(), 1);
    }

    void stop()
    {
        m_server->route("/slow", HttpReply { titled("slow"), "text/html", 200, {}, 60000 });
        ShownView shown;
        QWebEnginePage* page = shown.page();
        QSignalSpy started(page, &QWebEnginePage::loadStarted);
        QSignalSpy finished(page, &QWebEnginePage::loadFinished);
        page->load(m_server->url("/slow"));
        QTRY_COMPARE(m_server->requestCount("/slow"), 1);
        QVERIFY(page->isLoading());
        page->triggerAction(QWebEnginePage::Stop);
        QTRY_COMPARE(finished.count(), 1);
        QCOMPARE(finished.first().first().toBool(), false);
        QVERIFY(!page->isLoading());
    }

    void navigationType_data()
    {
        QTest::addColumn<QString>("trigger");
        QTest::addColumn<int>("type");
        QTest::newRow("load") << QStringLiteral("load") << int(QWebEnginePage::NavigationTypeTyped);
        QTest::newRow("link") << QStringLiteral("link") << int(QWebEnginePage::NavigationTypeLinkClicked);
        QTest::newRow("script") << QStringLiteral("script") << int(QWebEnginePage::NavigationTypeLinkClicked);
        QTest::newRow("form") << QStringLiteral("form") << int(QWebEnginePage::NavigationTypeFormSubmitted);
        QTest::newRow("reload") << QStringLiteral("reload") << int(QWebEnginePage::NavigationTypeReload);
        QTest::newRow("back") << QStringLiteral("back") << int(QWebEnginePage::NavigationTypeBackForward);
        QTest::newRow("redirect") << QStringLiteral("redirect") << int(QWebEnginePage::NavigationTypeRedirect);
    }

    void navigationType()
    {
        QFETCH(QString, trigger);
        QFETCH(int, type);
        m_server->route("/start", titled("start", "<a id=link href=/b>b</a><form id=form action=/b></form>"));
        m_server->route("/redirect", HttpReply { "", "text/html", 302, { { "Location", "/b" } } });
        auto* page = new RecordingPage;
        ShownView shown(page);
        QVERIFY(loadsOk(page, m_server->url("/start")));
        if (trigger == QLatin1String("back"))
            QVERIFY(loadsOk(page, m_server->url("/b")));
        page->requests.clear();

        const QHash<QString, std::function<void()>> triggers {
            { QStringLiteral("load"), [&] { page->load(m_server->url("/b")); } },
            { QStringLiteral("link"), [&] { evaluate(page, QStringLiteral("document.getElementById('link').click()")); } },
            { QStringLiteral("script"), [&] { evaluate(page, QStringLiteral("location.href = '/b'")); } },
            { QStringLiteral("form"), [&] { evaluate(page, QStringLiteral("document.getElementById('form').submit()")); } },
            { QStringLiteral("reload"), [&] { page->triggerAction(QWebEnginePage::Reload); } },
            { QStringLiteral("back"), [&] { page->triggerAction(QWebEnginePage::Back); } },
            { QStringLiteral("redirect"), [&] { page->load(m_server->url("/redirect")); } },
        };
        QVERIFY(loadsOk(page, triggers.value(trigger)));
        QVERIFY(!page->requests.isEmpty());
        QCOMPARE(int(page->requests.last().type), type);
        QVERIFY(page->requests.last().isMainFrame);
    }

    void blockedNavigation_data()
    {
        QTest::addColumn<QString>("trigger");
        QTest::newRow("load") << QStringLiteral("load");
        QTest::newRow("script") << QStringLiteral("script");
    }

    void blockedNavigation()
    {
        QFETCH(QString, trigger);
        m_server->route("/blocked", titled("blocked"));
        auto* page = new RecordingPage;
        ShownView shown(page);
        QVERIFY(loadsOk(page, m_server->url("/a")));
        if (trigger == QLatin1String("load"))
            page->load(m_server->url("/blocked"));
        else
            evaluate(page, QStringLiteral("location.href = '/blocked'"));
        QTRY_VERIFY(!page->requests.isEmpty());
        QTest::qWait(500);
        QCOMPARE(page->requests.last().url, m_server->url("/blocked"));
        QCOMPARE(m_server->requestCount("/blocked"), 0);
        QCOMPARE(page->url(), m_server->url("/a"));
        QCOMPARE(page->title(), QStringLiteral("a"));
        QCOMPARE(page->history()->count(), 1);
    }

    void subFrameNavigationRequest()
    {
        m_server->route("/framed", titled("framed", "<iframe src=/b></iframe>"));
        auto* page = new RecordingPage;
        ShownView shown(page);
        QVERIFY(loadsOk(page, m_server->url("/framed")));
        QTRY_COMPARE(m_server->requestCount("/b"), 1);
        QTRY_COMPARE(page->requests.size(), 2);
        QCOMPARE(page->requests.at(0).isMainFrame, true);
        QCOMPARE(page->requests.at(1).url, m_server->url("/b"));
        QCOMPARE(page->requests.at(1).isMainFrame, false);
    }

    void newWindowRequested_data()
    {
        QTest::addColumn<QString>("script");
        QTest::addColumn<int>("destination");
        QTest::newRow("window.open") << QStringLiteral("window.open('/b')") << int(QWebEngineNewWindowRequest::InNewTab);
        QTest::newRow("popup") << QStringLiteral("window.open('/b', '', 'width=300,height=200')")
                               << int(QWebEngineNewWindowRequest::InNewDialog);
        QTest::newRow("target=_blank")
            << QStringLiteral("const a = document.createElement('a'); a.href = '/b'; a.target = '_blank';"
                              "document.body.appendChild(a); a.click()")
            << int(QWebEngineNewWindowRequest::InNewTab);
    }

    void newWindowRequested()
    {
        QFETCH(QString, script);
        QFETCH(int, destination);
        ShownView shown;
        ShownView opened;
        QWebEnginePage* page = shown.page();
        page->settings()->setAttribute(QWebEngineSettings::JavascriptCanOpenWindows, true);
        QVERIFY(loadsOk(page, m_server->url("/a")));
        std::optional<QUrl> requestedUrl;
        std::optional<int> requestedDestination;
        connect(page, &QWebEnginePage::newWindowRequested, this, [&](QWebEngineNewWindowRequest& request) {
            requestedUrl = request.requestedUrl();
            requestedDestination = request.destination();
            request.openIn(opened.page());
        });
        evaluate(page, script);
        QTRY_VERIFY(requestedUrl.has_value());
        QCOMPARE(*requestedUrl, m_server->url("/b"));
        QCOMPARE(*requestedDestination, destination);
        QTRY_COMPARE(opened.page()->url(), m_server->url("/b"));
        QTRY_COMPARE(opened.page()->title(), QStringLiteral("b"));
        QCOMPARE(page->url(), m_server->url("/a"));
    }

    // A browser makes the popup's page while handling the request: the popup keeps window.opener
    void openerKept()
    {
        ShownView shown;
        QWebEnginePage* page = shown.page();
        page->settings()->setAttribute(QWebEngineSettings::JavascriptCanOpenWindows, true);
        QVERIFY(loadsOk(page, m_server->url("/a")));
        std::unique_ptr<ShownView> opened;
        connect(page, &QWebEnginePage::newWindowRequested, this, [&](QWebEngineNewWindowRequest& request) {
            opened = std::make_unique<ShownView>();
            request.openIn(opened->page());
        });
        evaluate(page, QStringLiteral("window.open('/b')"));
        QTRY_VERIFY(opened);
        QTRY_COMPARE(opened->page()->url(), m_server->url("/b"));
        QTRY_COMPARE(opened->page()->title(), QStringLiteral("b"));
        QCOMPARE(evaluate(opened->page(), QStringLiteral("window.opener !== null")), QVariant(true));
    }

    // A browser that makes more than one page while handling the request opens the window in any of them
    void windowOpenedInALaterPage()
    {
        ShownView shown;
        QWebEnginePage* page = shown.page();
        page->settings()->setAttribute(QWebEngineSettings::JavascriptCanOpenWindows, true);
        QVERIFY(loadsOk(page, m_server->url("/a")));
        std::unique_ptr<ShownView> first, opened;
        connect(page, &QWebEnginePage::newWindowRequested, this, [&](QWebEngineNewWindowRequest& request) {
            first = std::make_unique<ShownView>();
            opened = std::make_unique<ShownView>();
            request.openIn(opened->page());
        });
        evaluate(page, QStringLiteral("window.open('/b')"));
        QTRY_VERIFY(opened);
        QTRY_COMPARE(opened->page()->url(), m_server->url("/b"));
        QTRY_COMPARE(opened->page()->title(), QStringLiteral("b"));
        QCOMPARE(page->url(), m_server->url("/a"));
    }

    // Falkon leaves windows to the engine: with JavascriptCanOpenWindows off, its default, only a user's click
    // opens one, and a popup cannot open more, so a page cannot flood the screen with them
    void popupBlocking_data()
    {
        QTest::addColumn<bool>("canOpen");
        QTest::addColumn<QString>("script");
        QTest::addColumn<bool>("click");
        QTest::addColumn<int>("windows");
        const QString onClick = QStringLiteral("document.onclick = () => %1");
        QTest::newRow("on load") << false << QStringLiteral("window.open('/b')") << false << 0;
        QTest::newRow("on load, allowed") << true << QStringLiteral("window.open('/b')") << false << 1;
        QTest::newRow("click") << false << onClick.arg(QStringLiteral("window.open('/b')")) << true << 1;
        QTest::newRow("click opens five")
            << false << onClick.arg(QStringLiteral("{ for (let i = 0; i < 5; i++) window.open('/b?' + i) }")) << true << 1;
        QTest::newRow("timer after click")
            << false << onClick.arg(QStringLiteral("setTimeout(() => window.open('/b'), 500)")) << true << 1;
        QTest::newRow("popup opens more") << false << onClick.arg(QStringLiteral("window.open('/bomb')")) << true << 1;
        QTest::newRow("leaving the page")
            << false << QStringLiteral("onpagehide = () => window.open('/b'); ") + onClick.arg(QStringLiteral("location = '/a'"))
            << true << 0;
    }

    void popupBlocking()
    {
        QFETCH(bool, canOpen);
        QFETCH(QString, script);
        QFETCH(bool, click);
        QFETCH(int, windows);
        const int settleMs = 1500;
        m_server->route("/popups", titled("popups", "<script>" + script.toUtf8() + "</script>"));
        m_server->route("/bomb", titled("bomb", "<script>window.open('/b')</script>"));
        int requested = 0;
        std::vector<std::unique_ptr<ShownView>> popups;
        std::function<void(QWebEnginePage*)> watch = [&](QWebEnginePage* page) {
            page->settings()->setAttribute(QWebEngineSettings::JavascriptCanOpenWindows, canOpen);
            connect(page, &QWebEnginePage::newWindowRequested, this, [&](QWebEngineNewWindowRequest& request) {
                ++requested;
                if (request.requestedUrl().path() != QLatin1String("/bomb"))
                    return;
                popups.push_back(std::make_unique<ShownView>());
                watch(popups.back()->page());
                request.openIn(popups.back()->page());
            });
        };
        ShownView shown;
        shown.view.activateWindow();
        QVERIFY(QTest::qWaitForWindowActive(&shown.view));
        watch(shown.page());
        QVERIFY(loadsOk(shown.page(), m_server->url("/popups")));
        if (click)
            QVERIFY(clickPage(shown));
        QTest::qWait(settleMs);
        QCOMPARE(requested, windows);
    }

    // A page goes fullscreen only from a user's click
    void fullscreenNeedsGesture_data()
    {
        QTest::addColumn<bool>("click");
        QTest::addColumn<int>("requests");
        QTest::newRow("on load") << false << 0;
        QTest::newRow("click") << true << 1;
    }

    void fullscreenNeedsGesture()
    {
        QFETCH(bool, click);
        QFETCH(int, requests);
        const int settleMs = 1500;
        const QString request = QStringLiteral("document.documentElement.requestFullscreen().catch(() => {})");
        const QByteArray onClick = click ? "document.onclick = () => " : "";
        m_server->route("/full", titled("full", "<script>" + onClick + request.toUtf8() + "</script>"));
        ShownView shown;
        shown.page()->settings()->setAttribute(QWebEngineSettings::FullScreenSupportEnabled, true);
        int requested = 0;
        connect(shown.page(), &QWebEnginePage::fullScreenRequested, this, [&](QWebEngineFullScreenRequest request) {
            ++requested;
            request.reject();
        });
        QVERIFY(loadsOk(shown.page(), m_server->url("/full")));
        if (click)
            QVERIFY(clickPage(shown));
        QTest::qWait(settleMs);
        QCOMPARE(requested, requests);
    }

    // History a page pushes without the user's input does not hold the user back from leaving it
    void backSkipsUnvisitedEntries()
    {
        m_server->route("/trap", titled("trap", "<script>for (let i = 0; i < 5; i++) history.pushState({}, '', '?' + i)</script>"));
        ShownView shown;
        QWebEnginePage* page = shown.page();
        QVERIFY(loadsOk(page, m_server->url("/a")));
        QVERIFY(loadsOk(page, m_server->url("/trap")));
        QTRY_COMPARE(page->url().query(), QStringLiteral("4"));
        page->triggerAction(QWebEnginePage::Back);
        QTRY_COMPARE(page->url(), m_server->url("/a"));
    }

    void historySerialization()
    {
        QByteArray saved;
        {
            ShownView shown;
            for (const char* name : { "/a", "/b", "/c" })
                QVERIFY(loadsOk(shown.page(), m_server->url(name)));
            QVERIFY(loadsOk(shown.page(), [&] { shown.page()->history()->back(); }));
            QDataStream out(&saved, QIODevice::WriteOnly);
            out << *shown.page()->history();
        }
        QVERIFY(!saved.isEmpty());

        ShownView restored;
        QWebEngineHistory* history = restored.page()->history();
        QDataStream in(saved);
        in >> *history;
        QTRY_COMPARE(restored.page()->url(), m_server->url("/b"));
        QCOMPARE(history->count(), 3);
        QCOMPARE(history->currentItemIndex(), 1);
        QCOMPARE(history->itemAt(0).url(), m_server->url("/a"));
        QCOMPARE(history->itemAt(2).title(), QStringLiteral("c"));
        QVERIFY(loadsOk(restored.page(), [&] { history->back(); }));
        QCOMPARE(restored.page()->url(), m_server->url("/a"));
    }

    void historySerializationEdges()
    {
        ShownView shown;
        QVERIFY(loadsOk(shown.page(), m_server->url("/a")));
        QByteArray garbage("not a session");
        QDataStream in(garbage);
        in >> *shown.page()->history();
        QTest::qWait(300);
        QCOMPARE(shown.page()->url(), m_server->url("/a"));
        QCOMPARE(shown.page()->history()->count(), 1);
    }

private:
    std::unique_ptr<TestServer> m_server;
};

QTEST_MAIN(tst_Navigation)
#include "tst_navigation.moc"
