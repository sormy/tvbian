// runJavaScript's results and worlds, user scripts, and pages without JavaScript
#include "webtest.h"

#include <QTemporaryDir>
#include <QWebEngineProfile>
#include <QWebEngineScript>
#include <QWebEngineScriptCollection>
#include <QWebEngineSettings>

static const QString pageHtml = QStringLiteral("<html><head><title>js</title></head><body><p>text</p></body></html>");

static QWebEngineScript userScript(const QString& source, QWebEngineScript::InjectionPoint point,
    quint32 worldId = QWebEngineScript::MainWorld, bool subFrames = false)
{
    QWebEngineScript script;
    script.setName(QStringLiteral("test"));
    script.setSourceCode(source);
    script.setInjectionPoint(point);
    script.setWorldId(worldId);
    script.setRunsOnSubFrames(subFrames);
    return script;
}

// A page that keeps its console's messages
class ConsolePage : public QWebEnginePage {
public:
    using QWebEnginePage::QWebEnginePage;
    struct Message {
        JavaScriptConsoleMessageLevel level;
        QString text;
        bool operator==(const Message&) const = default;
    };
    QList<Message> messages;

protected:
    void javaScriptConsoleMessage(JavaScriptConsoleMessageLevel level, const QString& text, int, const QString&) override
    {
        messages.append({ level, text });
    }
};

class tst_JavaScript : public QObject {
    Q_OBJECT

private Q_SLOTS:
    void init() { m_server = std::make_unique<TestServer>(); }
    void cleanup() { m_server.reset(); }

    void results_data()
    {
        QTest::addColumn<QString>("script");
        QTest::addColumn<QVariant>("expected");
        QTest::newRow("integer") << QStringLiteral("6 * 7") << QVariant(42);
        QTest::newRow("negative") << QStringLiteral("-3") << QVariant(-3);
        QTest::newRow("double") << QStringLiteral("1.5") << QVariant(1.5);
        QTest::newRow("string") << QStringLiteral("'héllo ✓ ж'") << QVariant(QStringLiteral("héllo ✓ ж"));
        QTest::newRow("empty string") << QStringLiteral("''") << QVariant(QString());
        QTest::newRow("true") << QStringLiteral("1 < 2") << QVariant(true);
        QTest::newRow("false") << QStringLiteral("!document") << QVariant(false);
        QTest::newRow("array") << QStringLiteral("[1, 'a', true, [2]]")
                               << QVariant(QVariantList { 1, QStringLiteral("a"), true, QVariantList { 2 } });
        QTest::newRow("empty array") << QStringLiteral("[]") << QVariant(QVariantList());
        QTest::newRow("object") << QStringLiteral("({ a: 1, b: 'x', c: { d: [null] } })")
                                << QVariant(QVariantMap { { QStringLiteral("a"), 1 }, { QStringLiteral("b"), QStringLiteral("x") },
                                       { QStringLiteral("c"), QVariantMap { { QStringLiteral("d"), QVariantList { QVariant() } } } } });
        QTest::newRow("empty object") << QStringLiteral("({})") << QVariant(QVariantMap());
        QTest::newRow("null") << QStringLiteral("null") << QVariant();
        QTest::newRow("undefined") << QStringLiteral("undefined") << QVariant();
        QTest::newRow("thrown error") << QStringLiteral("throw new Error('boom')") << QVariant();
        QTest::newRow("syntax error") << QStringLiteral("1 +") << QVariant();
        QTest::newRow("function") << QStringLiteral("(function () {})") << QVariant();
        QTest::newRow("last statement") << QStringLiteral("var x = 2; x + 1") << QVariant(3);
        QTest::newRow("date") << QStringLiteral("new Date(1000)") << QVariant(1.0);
        QTest::newRow("DOM element") << QStringLiteral("document.body") << QVariant(QVariantMap());
    }

    void results()
    {
        QFETCH(QString, script);
        QFETCH(QVariant, expected);
        ShownView shown;
        QVERIFY(setsHtml(shown.page(), pageHtml));
        const QVariant result = evaluate(shown.page(), script);
        QCOMPARE(result, expected);
        QCOMPARE(result.isValid(), expected.isValid());
    }

    void callbackOnlyOnce()
    {
        ShownView shown;
        QVERIFY(setsHtml(shown.page(), pageHtml));
        int calls = 0;
        shown.page()->runJavaScript(QStringLiteral("1"), [&calls](const QVariant&) { ++calls; });
        shown.page()->runJavaScript(QStringLiteral("document.title = 'no callback'"));
        QTRY_COMPARE(calls, 1);
        QTRY_COMPARE(shown.page()->title(), QStringLiteral("no callback"));
        QTest::qWait(200);
        QCOMPARE(calls, 1);
    }

    void worlds_data()
    {
        QTest::addColumn<quint32>("worldId");
        QTest::newRow("main") << quint32(QWebEngineScript::MainWorld);
        QTest::newRow("application") << quint32(QWebEngineScript::ApplicationWorld);
        QTest::newRow("user") << quint32(QWebEngineScript::UserWorld);
        QTest::newRow("custom 42") << quint32(42);
    }

    // Every world sees the same document
    void worlds()
    {
        QFETCH(quint32, worldId);
        ShownView shown;
        QVERIFY(setsHtml(shown.page(), pageHtml));
        QCOMPARE(evaluate(shown.page(), QStringLiteral("document.title"), worldId), QVariant(QStringLiteral("js")));
        QCOMPARE(evaluate(shown.page(), QStringLiteral("document.body.dataset.world = 'seen'; 1"), worldId), QVariant(1));
        QCOMPARE(evaluate(shown.page(), QStringLiteral("document.body.dataset.world")), QVariant(QStringLiteral("seen")));
    }

    void worldIsolation_data()
    {
        QTest::addColumn<quint32>("setter");
        QTest::addColumn<quint32>("reader");
        QTest::addColumn<bool>("visible");
        const quint32 main = QWebEngineScript::MainWorld;
        const quint32 application = QWebEngineScript::ApplicationWorld;
        const quint32 user = QWebEngineScript::UserWorld;
        QTest::newRow("main to main") << main << main << true;
        QTest::newRow("application to application") << application << application << true;
        QTest::newRow("main to application") << main << application << false;
        QTest::newRow("application to main") << application << main << false;
        QTest::newRow("application to user") << application << user << false;
    }

    void worldIsolation()
    {
        QFETCH(quint32, setter);
        QFETCH(quint32, reader);
        QFETCH(bool, visible);
        ShownView shown;
        QVERIFY(setsHtml(shown.page(), pageHtml));
        evaluate(shown.page(), QStringLiteral("window.secret = 's'"), setter);
        QCOMPARE(evaluate(shown.page(), QStringLiteral("typeof window.secret"), reader),
            QVariant(visible ? QStringLiteral("string") : QStringLiteral("undefined")));
    }

    void javascriptDisabled_data()
    {
        QTest::addColumn<quint32>("worldId");
        QTest::addColumn<QVariant>("expected");
        QTest::newRow("main world") << quint32(QWebEngineScript::MainWorld) << QVariant();
        QTest::newRow("application world") << quint32(QWebEngineScript::ApplicationWorld) << QVariant(2);
    }

    // The page's scripts stop, and so do the application's in the main world
    void javascriptDisabled()
    {
        QFETCH(quint32, worldId);
        QFETCH(QVariant, expected);
        ShownView shown;
        shown.page()->settings()->setAttribute(QWebEngineSettings::JavascriptEnabled, false);
        QVERIFY(setsHtml(shown.page(),
            QStringLiteral("<title>static</title><script>document.title = 'ran'</script><img src=x onerror=\"document.title='ran'\">")));
        QTest::qWait(200);
        QCOMPARE(shown.page()->title(), QStringLiteral("static"));
        QCOMPARE(evaluate(shown.page(), QStringLiteral("1 + 1"), worldId), expected);
    }

    void javascriptReenabled()
    {
        ShownView shown;
        QWebEngineSettings* settings = shown.page()->settings();
        settings->setAttribute(QWebEngineSettings::JavascriptEnabled, false);
        QVERIFY(!settings->testAttribute(QWebEngineSettings::JavascriptEnabled));
        settings->resetAttribute(QWebEngineSettings::JavascriptEnabled);
        QVERIFY(settings->testAttribute(QWebEngineSettings::JavascriptEnabled));
        QVERIFY(setsHtml(shown.page(), QStringLiteral("<title>static</title><script>document.title = 'ran'</script>")));
        QTRY_COMPARE(shown.page()->title(), QStringLiteral("ran"));
    }

    void injectionPoint_data()
    {
        QTest::addColumn<int>("point");
        QTest::addColumn<quint32>("worldId");
        QTest::addColumn<QStringList>("readyStates");
        const QStringList loading { QStringLiteral("loading") };
        const QStringList loaded { QStringLiteral("interactive"), QStringLiteral("complete") };
        for (const auto& [world, worldName] : { std::pair { quint32(QWebEngineScript::MainWorld), "main" },
                 std::pair { quint32(QWebEngineScript::ApplicationWorld), "application" } }) {
            QTest::addRow("DocumentCreation, %s", worldName) << int(QWebEngineScript::DocumentCreation) << world << loading;
            QTest::addRow("DocumentReady, %s", worldName) << int(QWebEngineScript::DocumentReady) << world << loaded;
            QTest::addRow("Deferred, %s", worldName) << int(QWebEngineScript::Deferred) << world << loaded;
        }
    }

    // A user script runs once per load, at its point, in its world only
    void injectionPoint()
    {
        QFETCH(int, point);
        QFETCH(quint32, worldId);
        QFETCH(QStringList, readyStates);
        QWebEngineProfile profile;
        profile.scripts()->insert(userScript(
            QStringLiteral("window.runs = (window.runs || 0) + 1; window.readyStateSeen = document.readyState;"
                           "window.sawBody = Boolean(document.body);"),
            QWebEngineScript::InjectionPoint(point), worldId));
        ShownView shown(new QWebEnginePage(&profile));
        m_server->route("/page", pageHtml.toUtf8());
        QVERIFY(loadsOk(shown.page(), m_server->url("/page")));
        QTRY_COMPARE(evaluate(shown.page(), QStringLiteral("window.runs"), worldId), QVariant(1));
        const QString readyState = evaluate(shown.page(), QStringLiteral("window.readyStateSeen"), worldId).toString();
        QVERIFY2(readyStates.contains(readyState), qPrintable(readyState));
        QCOMPARE(evaluate(shown.page(), QStringLiteral("window.sawBody"), worldId).toBool(),
            point != QWebEngineScript::DocumentCreation);
        if (worldId != QWebEngineScript::MainWorld)
            QCOMPARE(evaluate(shown.page(), QStringLiteral("typeof window.runs")), QVariant(QStringLiteral("undefined")));
    }

    void documentCreationRunsBeforePageScripts()
    {
        QWebEngineProfile profile;
        profile.scripts()->insert(userScript(QStringLiteral("window.injected = 'early'"), QWebEngineScript::DocumentCreation));
        ShownView shown(new QWebEnginePage(&profile));
        QVERIFY(setsHtml(shown.page(), QStringLiteral("<script>document.title = String(window.injected)</script>")));
        QTRY_COMPARE(shown.page()->title(), QStringLiteral("early"));
    }

    void subFrames_data()
    {
        QTest::addColumn<bool>("runsOnSubFrames");
        QTest::newRow("main frame only") << false;
        QTest::newRow("sub-frames too") << true;
    }

    void subFrames()
    {
        QFETCH(bool, runsOnSubFrames);
        m_server->route("/framed", "<title>framed</title><iframe src=/frame onload=\"document.body.dataset.frameLoaded = 1\"></iframe>");
        m_server->route("/frame", "<p>frame</p>");
        QWebEngineProfile profile;
        profile.scripts()->insert(userScript(
            QStringLiteral("const root = window.top.document.documentElement;"
                           "root.dataset.injected = (root.dataset.injected || '') + (window === window.top ? 'top ' : 'frame ');"),
            QWebEngineScript::DocumentReady, QWebEngineScript::MainWorld, runsOnSubFrames));
        ShownView shown(new QWebEnginePage(&profile));
        QVERIFY(loadsOk(shown.page(), m_server->url("/framed")));
        QTRY_COMPARE(evaluate(shown.page(), QStringLiteral("document.body.dataset.frameLoaded")), QVariant(QStringLiteral("1")));
        QTest::qWait(200);
        const QString injected = evaluate(shown.page(), QStringLiteral("document.documentElement.dataset.injected")).toString();
        QCOMPARE(injected.split(QLatin1Char(' '), Qt::SkipEmptyParts).count(QStringLiteral("top")), 1);
        QCOMPARE(injected.contains(QLatin1String("frame")), runsOnSubFrames);
    }

    void headerUrls_data()
    {
        QTest::addColumn<QString>("header");
        QTest::addColumn<bool>("runs");
        QTest::newRow("no header") << QString() << true;
        QTest::newRow("@include this page") << QStringLiteral("@include %1") << true;
        QTest::newRow("@include another page") << QStringLiteral("@include %1/other") << false;
        QTest::newRow("@include with ?, not a wildcard") << QStringLiteral("@include *pag?") << false;
        QTest::newRow("@include ending in the path") << QStringLiteral("@include */page") << true;
        QTest::newRow("@include an application's page") << QStringLiteral("@include falkon:speeddial") << false;
        QTest::newRow("@exclude this page") << QStringLiteral("@exclude */page") << false;
        QTest::newRow("@include, then @exclude it") << QStringLiteral("@include *\n// @exclude %1") << false;
        QTest::newRow("@match any host") << QStringLiteral("@match *://*/page") << true;
        QTest::newRow("@match another path") << QStringLiteral("@match *://*/other") << false;
        QTest::newRow("@match <all_urls>") << QStringLiteral("@match <all_urls>") << true;
        QTest::newRow("@match malformed") << QStringLiteral("@match page") << false;
    }

    // A Greasemonkey header's URLs pick the pages a script runs on, as in QtWebEngine
    void headerUrls()
    {
        QFETCH(QString, header);
        QFETCH(bool, runs);
        m_server->route("/page", pageHtml.toUtf8());
        const QUrl url = m_server->url("/page");
        const QString source = header.isEmpty()
            ? QStringLiteral("window.ran = true;")
            : QStringLiteral("// ==UserScript==\n// %1\n// ==/UserScript==\nwindow.ran = true;").arg(QString(header).replace(QLatin1String("%1"), url.toString()));
        QWebEngineProfile profile;
        profile.scripts()->insert(userScript(source, QWebEngineScript::DocumentReady));
        ShownView shown(new QWebEnginePage(&profile));
        QVERIFY(loadsOk(shown.page(), url));
        QCOMPARE(evaluate(shown.page(), QStringLiteral("window.ran === true")), QVariant(runs));
    }

    void headerSettings()
    {
        QWebEngineScript script;
        script.setSourceCode(
            QStringLiteral("// ==UserScript==\n// @name   from header\n// @run-at document-start\n// ==/UserScript==\n"));
        QCOMPARE(script.name(), QStringLiteral("from header"));
        QCOMPARE(script.injectionPoint(), QWebEngineScript::DocumentCreation);
        script.setSourceCode(QStringLiteral("// ==UserScript==\n// @run-at document-idle\n// ==/UserScript==\n"));
        QCOMPARE(script.injectionPoint(), QWebEngineScript::Deferred);
    }

    void scriptCollection()
    {
        QWebEngineProfile profile;
        QWebEngineScriptCollection* scripts = profile.scripts();
        const QWebEngineScript first = userScript(QStringLiteral("window.first = true"), QWebEngineScript::DocumentReady);
        QWebEngineScript second = userScript(QStringLiteral("window.second = true"), QWebEngineScript::DocumentReady);
        second.setName(QStringLiteral("second"));
        QVERIFY(scripts->isEmpty());
        scripts->insert({ first, second });
        QCOMPARE(scripts->count(), 2);
        QVERIFY(scripts->contains(first));
        QCOMPARE(scripts->find(QStringLiteral("second")).size(), 1);
        QVERIFY(scripts->find(QStringLiteral("none")).isEmpty());

        ShownView shown(new QWebEnginePage(&profile));
        QVERIFY(setsHtml(shown.page(), pageHtml));
        QTRY_COMPARE(evaluate(shown.page(), QStringLiteral("[window.first, window.second]")), QVariant(QVariantList { true, true }));

        QVERIFY(scripts->remove(first));
        QVERIFY(!scripts->remove(first));
        QVERIFY(setsHtml(shown.page(), pageHtml));
        QCOMPARE(evaluate(shown.page(), QStringLiteral("[typeof window.first, window.second]")),
            QVariant(QVariantList { QStringLiteral("undefined"), true }));

        scripts->clear();
        QVERIFY(scripts->isEmpty());
        QVERIFY(setsHtml(shown.page(), pageHtml));
        QCOMPARE(evaluate(shown.page(), QStringLiteral("typeof window.second")), QVariant(QStringLiteral("undefined")));
    }

    void consoleMessages()
    {
        m_server->route("/console", "<script>console.log('info'); console.warn('warning'); console.error('error');</script>");
        // a profile on disk: WebKit keeps an off-the-record page's console from the application
        QTemporaryDir storage;
        QWebEngineProfile profile(QStringLiteral("console"));
        profile.setPersistentStoragePath(storage.path());
        auto* page = new ConsolePage(&profile);
        ShownView shown(page);
        QVERIFY(loadsOk(page, m_server->url("/console")));
        using Message = ConsolePage::Message;
        const QList<Message> expected {
            { QWebEnginePage::InfoMessageLevel, QStringLiteral("info") },
            { QWebEnginePage::WarningMessageLevel, QStringLiteral("warning") },
            { QWebEnginePage::ErrorMessageLevel, QStringLiteral("error") },
        };
        QTRY_COMPARE(page->messages.size(), expected.size());
        QVERIFY(page->messages == expected);
    }

private:
    std::unique_ptr<TestServer> m_server;
};

QTEST_MAIN(tst_JavaScript)
#include "tst_javascript.moc"
