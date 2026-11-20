// Custom URL schemes: registration flags, handlers' replies, failures and redirects
#include "webtest.h"

#include <QBuffer>
#include <QWebEngineHistory>
#include <QWebEngineProfile>
#include <QWebEngineUrlRequestJob>
#include <QWebEngineUrlScheme>
#include <QWebEngineUrlSchemeHandler>

using Scheme = QWebEngineUrlScheme;

static const Scheme::Flags secureFlags = Scheme::SecureScheme | Scheme::CorsEnabled | Scheme::FetchApiAllowed;

// Schemes must be known before the application starts
static void registerSchemes()
{
    for (const auto& [name, flags] : { std::pair { "plain", Scheme::Flags() }, std::pair { "secure", secureFlags } }) {
        Scheme scheme(name);
        scheme.setSyntax(Scheme::Syntax::Host);
        scheme.setFlags(flags);
        Scheme::registerScheme(scheme);
    }
}
Q_CONSTRUCTOR_FUNCTION(registerSchemes)

// Answers by path: a page, data, a failure or a redirect
class Handler : public QWebEngineUrlSchemeHandler {
public:
    QList<QUrl> urls;
    QList<QByteArray> methods;

    void requestStarted(QWebEngineUrlRequestJob* job) override
    {
        urls.append(job->requestUrl());
        methods.append(job->requestMethod());
        const QString path = job->requestUrl().path();
        if (path == QLatin1String("/page"))
            reply(job, "text/html", "<title>scheme page</title><p>from the handler</p>");
        else if (path == QLatin1String("/data"))
            reply(job, "text/plain", "payload");
        else if (path == QLatin1String("/denied"))
            job->fail(QWebEngineUrlRequestJob::RequestDenied);
        else if (path == QLatin1String("/aborted"))
            job->fail(QWebEngineUrlRequestJob::RequestAborted);
        else if (path == QLatin1String("/redirect"))
            job->redirect(QUrl(job->requestUrl().scheme() + QLatin1String("://app/page")));
        else
            job->fail(QWebEngineUrlRequestJob::UrlNotFound);
    }

private:
    static void reply(QWebEngineUrlRequestJob* job, const QByteArray& type, const QByteArray& data)
    {
        auto* buffer = new QBuffer(job);
        buffer->setData(data);
        job->reply(type, buffer);
    }
};

class tst_Schemes : public QObject {
    Q_OBJECT

private Q_SLOTS:
    void init()
    {
        m_profile = std::make_unique<QWebEngineProfile>();
        m_handler = std::make_unique<Handler>();
        for (const char* scheme : { "plain", "secure" })
            m_profile->installUrlSchemeHandler(scheme, m_handler.get());
    }

    void cleanup()
    {
        m_profile.reset();
        m_handler.reset();
    }

    void registration()
    {
        QCOMPARE(Scheme::schemeByName("secure").name(), QByteArray("secure"));
        QCOMPARE(Scheme::schemeByName("secure").flags(), secureFlags);
        QCOMPARE(Scheme::schemeByName("secure").syntax(), Scheme::Syntax::Host);
        QCOMPARE(Scheme::schemeByName("plain").flags(), Scheme::Flags());
        QVERIFY(Scheme::schemeByName("unregistered").name().isEmpty());
        QCOMPARE(m_profile->urlSchemeHandler("plain"), m_handler.get());
        QCOMPARE(m_profile->urlSchemeHandler("unregistered"), nullptr);
    }

    void reply_data()
    {
        QTest::addColumn<QString>("scheme");
        QTest::newRow("plain") << QStringLiteral("plain");
        QTest::newRow("secure") << QStringLiteral("secure");
    }

    void reply()
    {
        QFETCH(QString, scheme);
        ShownView shown(new QWebEnginePage(m_profile.get()));
        const QUrl url(scheme + QLatin1String("://app/page"));
        QVERIFY(loadsOk(shown.page(), url));
        QCOMPARE(shown.page()->url(), url);
        QCOMPARE(shown.page()->title(), QStringLiteral("scheme page"));
        QCOMPARE(m_handler->urls, QList<QUrl> { url });
        QCOMPARE(m_handler->methods, QList<QByteArray> { "GET" });
    }

    void fail_data()
    {
        QTest::addColumn<QString>("path");
        QTest::newRow("not found") << QStringLiteral("/missing");
        QTest::newRow("denied") << QStringLiteral("/denied");
        QTest::newRow("aborted") << QStringLiteral("/aborted");
    }

    void fail()
    {
        QFETCH(QString, path);
        ShownView shown(new QWebEnginePage(m_profile.get()));
        QCOMPARE(loadsOk(shown.page(), QUrl(QLatin1String("plain://app") + path)), false);
        QCOMPARE(m_handler->urls.size(), 1);
    }

    void redirect()
    {
        ShownView shown(new QWebEnginePage(m_profile.get()));
        QSignalSpy finished(shown.page(), &QWebEnginePage::loadFinished);
        shown.page()->load(QUrl(QStringLiteral("plain://app/redirect")));
        QTRY_COMPARE(shown.page()->title(), QStringLiteral("scheme page"));
        QTest::qWait(300);
        QCOMPARE(shown.page()->url(), QUrl(QStringLiteral("plain://app/page")));
        QCOMPARE(finished.count(), 1);
        QCOMPARE(finished.first().first().toBool(), true);
        QCOMPARE(shown.page()->history()->count(), 1);
    }

    void handlerRemoved()
    {
        m_profile->removeUrlSchemeHandler(m_handler.get());
        QCOMPARE(m_profile->urlSchemeHandler("plain"), nullptr);
        ShownView shown(new QWebEnginePage(m_profile.get()));
        QCOMPARE(loadsOk(shown.page(), QUrl(QStringLiteral("plain://app/page"))), false);
        QVERIFY(m_handler->urls.isEmpty());
    }

    void secureContext_data()
    {
        QTest::addColumn<QString>("scheme");
        QTest::addColumn<bool>("secure");
        QTest::newRow("plain") << QStringLiteral("plain") << false;
        QTest::newRow("secure") << QStringLiteral("secure") << true;
    }

    void secureContext()
    {
        QFETCH(QString, scheme);
        QFETCH(bool, secure);
        ShownView shown(new QWebEnginePage(m_profile.get()));
        QVERIFY(loadsOk(shown.page(), QUrl(scheme + QLatin1String("://app/page"))));
        QCOMPARE(evaluate(shown.page(), QStringLiteral("window.isSecureContext")), QVariant(secure));
    }

    void fetch_data()
    {
        QTest::addColumn<QString>("scheme");
        QTest::addColumn<QString>("result");
        QTest::newRow("FetchApiAllowed") << QStringLiteral("secure") << QStringLiteral("payload");
        QTest::newRow("no flags") << QStringLiteral("plain") << QStringLiteral("error");
    }

    void fetch()
    {
        QFETCH(QString, scheme);
        QFETCH(QString, result);
        ShownView shown(new QWebEnginePage(m_profile.get()));
        QVERIFY(loadsOk(shown.page(), QUrl(scheme + QLatin1String("://app/page"))));
        evaluate(shown.page(), QStringLiteral("fetch('%1://app/data').then(r => r.text()).then(text => document.title = text,"
                                              "() => document.title = 'error')").arg(scheme));
        QTRY_COMPARE(shown.page()->title(), result);
    }

    void subresourceFromHttpPage_data()
    {
        QTest::addColumn<QString>("scheme");
        QTest::newRow("plain") << QStringLiteral("plain");
        QTest::newRow("secure") << QStringLiteral("secure");
    }

    void subresourceFromHttpPage()
    {
        QFETCH(QString, scheme);
        TestServer server;
        server.route("/page", QStringLiteral("<iframe src=\"%1://app/page\"></iframe>").arg(scheme).toUtf8());
        ShownView shown(new QWebEnginePage(m_profile.get()));
        QVERIFY(loadsOk(shown.page(), server.url("/page")));
        QTRY_COMPARE(m_handler->urls, QList<QUrl> { QUrl(scheme + QLatin1String("://app/page")) });
    }

    // The application's resources, built in like QtWebEngine's
    void qrc()
    {
        ShownView shown(new QWebEnginePage(m_profile.get()));
        const QUrl url(QStringLiteral("qrc:/schemes/page.html"));
        QVERIFY(loadsOk(shown.page(), url));
        QCOMPARE(shown.page()->url(), url);
        QCOMPARE(shown.page()->title(), QStringLiteral("qrc page"));
        QTRY_COMPARE(evaluate(shown.page(), QStringLiteral("document.documentElement.dataset.script")), QVariant(QStringLiteral("ran")));
    }

    void qrcMissing()
    {
        ShownView shown(new QWebEnginePage(m_profile.get()));
        QCOMPARE(loadsOk(shown.page(), QUrl(QStringLiteral("qrc:/schemes/missing.html"))), false);
    }

private:
    std::unique_ptr<QWebEngineProfile> m_profile;
    std::unique_ptr<Handler> m_handler;
};

QTEST_MAIN(tst_Schemes)
#include "tst_schemes.moc"
