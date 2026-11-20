// The profile's cookie store: cookies set by C++, by the server and by scripts, their signals and deletion
#include "webtest.h"

#include <QNetworkCookie>
#include <QWebEngineCookieStore>
#include <QWebEngineProfile>

static QStringList namesOf(const QSignalSpy& spy)
{
    QStringList names;
    for (const QList<QVariant>& arguments : spy)
        names.append(QString::fromUtf8(arguments.first().value<QNetworkCookie>().name()));
    return names;
}

class tst_Cookies : public QObject {
    Q_OBJECT

private Q_SLOTS:
    void init()
    {
        m_server = std::make_unique<TestServer>();
        m_server->route("/page", "<title>cookies</title>");
        m_server->route("/set", HttpReply { "<title>set</title>", "text/html", 200, { { "Set-Cookie", "server=1; Path=/" } } });
        m_profile = std::make_unique<QWebEngineProfile>();
    }

    void cleanup()
    {
        m_profile.reset();
        m_server.reset();
    }

    void addedFromServer()
    {
        QSignalSpy added(m_profile->cookieStore(), &QWebEngineCookieStore::cookieAdded);
        ShownView shown(new QWebEnginePage(m_profile.get()));
        QVERIFY(loadsOk(shown.page(), m_server->url("/set")));
        QTRY_COMPARE(namesOf(added), QStringList { QStringLiteral("server") });
        const auto cookie = added.first().first().value<QNetworkCookie>();
        QCOMPARE(cookie.value(), QByteArray("1"));
        QCOMPARE(cookie.domain(), QStringLiteral("127.0.0.1"));
        QCOMPARE(cookie.path(), QStringLiteral("/"));
        QVERIFY(cookie.isSessionCookie());
        QCOMPARE(evaluate(shown.page(), QStringLiteral("document.cookie")), QVariant(QStringLiteral("server=1")));
    }

    void addedFromScript()
    {
        QSignalSpy added(m_profile->cookieStore(), &QWebEngineCookieStore::cookieAdded);
        ShownView shown(new QWebEnginePage(m_profile.get()));
        QVERIFY(loadsOk(shown.page(), m_server->url("/page")));
        evaluate(shown.page(), QStringLiteral("document.cookie = 'script=ж; max-age=3600'"));
        QTRY_COMPARE(namesOf(added), QStringList { QStringLiteral("script") });
        QVERIFY(!added.first().first().value<QNetworkCookie>().isSessionCookie());
    }

    void setFromCpp_data()
    {
        QTest::addColumn<bool>("withOrigin");
        QTest::addColumn<bool>("httpOnly");
        QTest::addColumn<QString>("visible");
        QTest::newRow("domain cookie") << false << false << QStringLiteral("cpp=2");
        QTest::newRow("origin only") << true << false << QStringLiteral("cpp=2");
        QTest::newRow("http only") << false << true << QString();
    }

    void setFromCpp()
    {
        QFETCH(bool, withOrigin);
        QFETCH(bool, httpOnly);
        QFETCH(QString, visible);
        ShownView shown(new QWebEnginePage(m_profile.get()));
        QSignalSpy added(m_profile->cookieStore(), &QWebEngineCookieStore::cookieAdded);
        QNetworkCookie cookie("cpp", "2");
        cookie.setPath(QStringLiteral("/"));
        cookie.setHttpOnly(httpOnly);
        if (!withOrigin)
            cookie.setDomain(QStringLiteral("127.0.0.1"));
        m_profile->cookieStore()->setCookie(cookie, withOrigin ? m_server->url("/") : QUrl());
        QTRY_COMPARE(namesOf(added), QStringList { QStringLiteral("cpp") });
        QVERIFY(loadsOk(shown.page(), m_server->url("/page")));
        QCOMPARE(m_server->requestHeader("/page", "Cookie"), QByteArray("cpp=2"));
        QCOMPARE(evaluate(shown.page(), QStringLiteral("document.cookie")), QVariant(visible));
    }

    void deleteCookie()
    {
        QSignalSpy added(m_profile->cookieStore(), &QWebEngineCookieStore::cookieAdded);
        QSignalSpy removed(m_profile->cookieStore(), &QWebEngineCookieStore::cookieRemoved);
        ShownView shown(new QWebEnginePage(m_profile.get()));
        QVERIFY(loadsOk(shown.page(), m_server->url("/set")));
        QTRY_COMPARE(added.count(), 1);
        m_profile->cookieStore()->deleteCookie(added.first().first().value<QNetworkCookie>());
        QTRY_COMPARE(namesOf(removed), QStringList { QStringLiteral("server") });
        QVERIFY(loadsOk(shown.page(), m_server->url("/page")));
        QCOMPARE(m_server->requestHeader("/page", "Cookie"), QByteArray());
        QCOMPARE(evaluate(shown.page(), QStringLiteral("document.cookie")), QVariant(QString()));
    }

    void deleteSessionCookies()
    {
        QSignalSpy added(m_profile->cookieStore(), &QWebEngineCookieStore::cookieAdded);
        QSignalSpy removed(m_profile->cookieStore(), &QWebEngineCookieStore::cookieRemoved);
        ShownView shown(new QWebEnginePage(m_profile.get()));
        QVERIFY(loadsOk(shown.page(), m_server->url("/set")));
        evaluate(shown.page(), QStringLiteral("document.cookie = 'kept=1; max-age=3600'"));
        QTRY_COMPARE(added.count(), 2);
        m_profile->cookieStore()->deleteSessionCookies();
        QTRY_COMPARE(namesOf(removed), QStringList { QStringLiteral("server") });
        QCOMPARE(evaluate(shown.page(), QStringLiteral("document.cookie")), QVariant(QStringLiteral("kept=1")));
    }

    void deleteAllCookies()
    {
        QSignalSpy added(m_profile->cookieStore(), &QWebEngineCookieStore::cookieAdded);
        QSignalSpy removed(m_profile->cookieStore(), &QWebEngineCookieStore::cookieRemoved);
        ShownView shown(new QWebEnginePage(m_profile.get()));
        QVERIFY(loadsOk(shown.page(), m_server->url("/set")));
        evaluate(shown.page(), QStringLiteral("document.cookie = 'other=1'"));
        QTRY_COMPARE(added.count(), 2);
        m_profile->cookieStore()->deleteAllCookies();
        QTRY_COMPARE(removed.count(), 2);
        QCOMPARE(evaluate(shown.page(), QStringLiteral("document.cookie")), QVariant(QString()));
    }

    void loadAllCookies()
    {
        ShownView shown(new QWebEnginePage(m_profile.get()));
        QNetworkCookie cookie("loaded", "1");
        cookie.setDomain(QStringLiteral("127.0.0.1"));
        m_profile->cookieStore()->setCookie(cookie);
        QSignalSpy added(m_profile->cookieStore(), &QWebEngineCookieStore::cookieAdded);
        QTRY_COMPARE(added.count(), 1);
        m_profile->cookieStore()->loadAllCookies();
        QTest::qWait(500);
        QCOMPARE(namesOf(added), QStringList { QStringLiteral("loaded") });
    }

private:
    std::unique_ptr<TestServer> m_server;
    std::unique_ptr<QWebEngineProfile> m_profile;
};

QTEST_MAIN(tst_Cookies)
#include "tst_cookies.moc"
