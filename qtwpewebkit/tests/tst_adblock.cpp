// QtWpeWebKit's Adblock Plus filters: blocking requests, hiding elements, and their exceptions
#include "webtest.h"

#include <QStandardPaths>
#include <QWebEngineProfile>

static const QByteArray dot = QByteArray::fromBase64(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAAABJRU5ErkJggg==");

static const QString filters = QStringLiteral(R"(! a small list
/ads/*
@@/ads/allowed.png
##.ad-box
##.sponsor
127.0.0.1#@#.sponsor
)");

static void routePage(TestServer& server)
{
    for (const char* path : { "/ads/banner.png", "/ads/allowed.png", "/images/photo.png" })
        server.route(path, HttpReply { dot, "image/png" });
    server.route("/page", R"(<title>adblock</title>
<img id=banner src=/ads/banner.png><img id=allowed src=/ads/allowed.png><img id=photo src=/images/photo.png>
<div class=ad-box id=box>ad</div><div class=sponsor id=sponsor>sponsor</div><div id=content>content</div>)");
}

static QString displayOf(QWebEnginePage* page, const QString& id)
{
    return evaluate(page, QStringLiteral("getComputedStyle(document.getElementById('%1')).display").arg(id)).toString();
}

class tst_Adblock : public QObject {
    Q_OBJECT

private Q_SLOTS:
    void initTestCase() { QStandardPaths::setTestModeEnabled(true); }

    void filtersApply()
    {
        QWebEngineProfile profile;
        profile.setAdblockFilters(filters);
        ShownView shown(new QWebEnginePage(&profile));
        QWebEnginePage* page = shown.page();

        // WebKit compiles the filters in the background: until then pages load unfiltered
        TestServer warmUp;
        routePage(warmUp);
        QTRY_VERIFY_WITH_TIMEOUT(loadsOk(page, warmUp.url("/page")) && displayOf(page, QStringLiteral("box")) == QLatin1String("none"),
            60000);

        TestServer server;
        routePage(server);
        QVERIFY(loadsOk(page, server.url("/page")));
        QTRY_COMPARE(server.requestCount("/images/photo.png"), 1);
        QTRY_COMPARE(server.requestCount("/ads/allowed.png"), 1);
        QCOMPARE(server.requestCount("/ads/banner.png"), 0);
        QCOMPARE(evaluate(page, QStringLiteral("document.getElementById('banner').naturalWidth")), QVariant(0));
        QCOMPARE(displayOf(page, QStringLiteral("box")), QStringLiteral("none"));
        QCOMPARE(displayOf(page, QStringLiteral("sponsor")), QStringLiteral("block"));
        QCOMPARE(displayOf(page, QStringLiteral("content")), QStringLiteral("block"));
    }

    void filtersRemoved()
    {
        QWebEngineProfile profile;
        profile.setAdblockFilters(filters);
        profile.setAdblockFilters(QString());
        ShownView shown(new QWebEnginePage(&profile));
        // Long enough for a compilation of the first filters, which must not apply any more
        QTest::qWait(2000);
        TestServer server;
        routePage(server);
        QVERIFY(loadsOk(shown.page(), server.url("/page")));
        QTRY_COMPARE(server.requestCount("/ads/banner.png"), 1);
        QCOMPARE(displayOf(shown.page(), QStringLiteral("box")), QStringLiteral("block"));
    }
};

QTEST_MAIN(tst_Adblock)
#include "tst_adblock.moc"
