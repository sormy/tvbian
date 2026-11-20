// Request interceptors: what they see of a page's requests, and blocking, redirecting and setting headers
#include "webtest.h"

#include <QMutex>
#include <QWebEngineProfile>
#include <QWebEngineUrlRequestInterceptor>

static const QByteArray dot = QByteArray::fromBase64(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAAABJRU5ErkJggg==");

// Records what it sees; blocks paths with "blocked", redirects "/moved.png" to "/dot.png" and adds a header.
// qtwpewebkit calls interceptors on a thread of its own
class Interceptor : public QWebEngineUrlRequestInterceptor {
public:
    struct Request {
        QUrl url;
        QUrl firstPartyUrl;
        QByteArray method;
        QWebEngineUrlRequestInfo::ResourceType type;
        QString interceptor;
    };

    explicit Interceptor(const QString& name)
        : m_name(name)
    {
    }

    void interceptRequest(QWebEngineUrlRequestInfo& info) override
    {
        {
            QMutexLocker locker(&m_mutex);
            m_seen->append({ info.requestUrl(), info.firstPartyUrl(), info.requestMethod(), info.resourceType(), m_name });
        }
        const QString path = info.requestUrl().path();
        if (path.contains(QLatin1String("blocked")))
            info.block(true);
        else if (path == QLatin1String("/moved.png"))
            info.redirect(info.requestUrl().resolved(QUrl(QStringLiteral("/dot.png"))));
        info.setHttpHeader("X-Intercepted-By", m_name.toUtf8());
    }

    // Shared, to see the order of a profile's and a page's interceptors
    void recordInto(QList<Request>* seen) { m_seen = seen; }

    QList<Request> requests() const
    {
        QMutexLocker locker(&m_mutex);
        return *m_seen;
    }

    std::optional<Request> requestFor(const QUrl& url) const
    {
        for (const Request& request : requests()) {
            if (request.url == url)
                return request;
        }
        return std::nullopt;
    }

private:
    QString m_name;
    mutable QMutex m_mutex;
    QList<Request> m_ownRequests;
    QList<Request>* m_seen = &m_ownRequests;
};

class tst_Interception : public QObject {
    Q_OBJECT

private Q_SLOTS:
    void init()
    {
        m_server = std::make_unique<TestServer>();
        m_server->route("/dot.png", HttpReply { dot, "image/png" });
        m_server->route("/blocked.png", HttpReply { dot, "image/png" });
        m_server->route("/blocked", "<title>blocked</title>");
        m_server->route("/page", "<title>page</title><img id=img src=/dot.png>");
        m_profile = std::make_unique<QWebEngineProfile>();
        m_interceptor = std::make_unique<Interceptor>(QStringLiteral("profile"));
        m_profile->setUrlRequestInterceptor(m_interceptor.get());
    }

    void cleanup()
    {
        m_profile.reset();
        m_interceptor.reset();
        m_server.reset();
    }

    void mainAndSubresourceRequests()
    {
        ShownView shown(new QWebEnginePage(m_profile.get()));
        const QUrl page = m_server->url("/page");
        QVERIFY(loadsOk(shown.page(), page));
        QTRY_VERIFY(m_interceptor->requestFor(m_server->url("/dot.png")).has_value());

        const auto main = m_interceptor->requestFor(page);
        QVERIFY(main.has_value());
        QCOMPARE(main->firstPartyUrl, page);
        QCOMPARE(main->method, QByteArray("GET"));
        QCOMPARE(main->type, QWebEngineUrlRequestInfo::ResourceTypeMainFrame);
        const auto image = m_interceptor->requestFor(m_server->url("/dot.png"));
        QCOMPARE(image->firstPartyUrl, page);
        QCOMPARE(image->method, QByteArray("GET"));
        QCOMPARE(image->type, QWebEngineUrlRequestInfo::ResourceTypeImage);
    }

    void method()
    {
        m_server->route("/posted", "ok");
        ShownView shown(new QWebEnginePage(m_profile.get()));
        QVERIFY(loadsOk(shown.page(), m_server->url("/page")));
        evaluate(shown.page(), QStringLiteral("fetch('/posted', { method: 'POST', body: 'x' }); 1"));
        QTRY_VERIFY(m_interceptor->requestFor(m_server->url("/posted")).has_value());
        QCOMPARE(m_interceptor->requestFor(m_server->url("/posted"))->method, QByteArray("POST"));
        QCOMPARE(m_interceptor->requestFor(m_server->url("/posted"))->firstPartyUrl, m_server->url("/page"));
    }

    void blockSubresource()
    {
        m_server->route("/image", "<img id=img src=/blocked.png onerror=\"document.title = 'failed'\">");
        ShownView shown(new QWebEnginePage(m_profile.get()));
        QVERIFY(loadsOk(shown.page(), m_server->url("/image")));
        QTRY_COMPARE(shown.page()->title(), QStringLiteral("failed"));
        QVERIFY(m_interceptor->requestFor(m_server->url("/blocked.png")).has_value());
        QCOMPARE(m_server->requestCount("/blocked.png"), 0);
    }

    void blockMainFrame()
    {
        ShownView shown(new QWebEnginePage(m_profile.get()));
        QCOMPARE(loadsOk(shown.page(), m_server->url("/blocked")), false);
        QVERIFY(m_interceptor->requestFor(m_server->url("/blocked")).has_value());
        QCOMPARE(m_server->requestCount("/blocked"), 0);
    }

    void redirect()
    {
        m_server->route("/with-moved", "<img id=img src=/moved.png>");
        ShownView shown(new QWebEnginePage(m_profile.get()));
        QVERIFY(loadsOk(shown.page(), m_server->url("/with-moved")));
        QTRY_COMPARE(evaluate(shown.page(), QStringLiteral("document.getElementById('img').naturalWidth")), QVariant(1));
        QCOMPARE(m_server->requestCount("/moved.png"), 0);
        QCOMPARE(m_server->requestCount("/dot.png"), 1);
    }

    void header()
    {
        ShownView shown(new QWebEnginePage(m_profile.get()));
        QVERIFY(loadsOk(shown.page(), m_server->url("/page")));
        QTRY_COMPARE(m_server->requestCount("/dot.png"), 1);
        QCOMPARE(m_server->requestHeader("/page", "X-Intercepted-By"), QByteArray("profile"));
        QCOMPARE(m_server->requestHeader("/dot.png", "X-Intercepted-By"), QByteArray("profile"));
    }

    // The profile's interceptor decides first, the page's last
    void profileThenPage()
    {
        QList<Interceptor::Request> seen;
        m_interceptor->recordInto(&seen);
        Interceptor pageInterceptor(QStringLiteral("page"));
        pageInterceptor.recordInto(&seen);
        auto* page = new QWebEnginePage(m_profile.get());
        page->setUrlRequestInterceptor(&pageInterceptor);
        ShownView shown(page);
        QVERIFY(loadsOk(page, m_server->url("/page")));
        QTRY_COMPARE(m_server->requestCount("/dot.png"), 1);
        QStringList order;
        for (const Interceptor::Request& request : m_interceptor->requests()) {
            if (request.url == m_server->url("/page"))
                order.append(request.interceptor);
        }
        QCOMPARE(order, (QStringList { QStringLiteral("profile"), QStringLiteral("page") }));
        QCOMPARE(m_server->requestHeader("/page", "X-Intercepted-By"), QByteArray("page"));
        page->setUrlRequestInterceptor(nullptr);
    }

private:
    std::unique_ptr<TestServer> m_server;
    std::unique_ptr<QWebEngineProfile> m_profile;
    std::unique_ptr<Interceptor> m_interceptor;
};

QTEST_MAIN(tst_Interception)
#include "tst_interception.moc"
