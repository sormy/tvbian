// What the tests share: a local HTTP server and waits on a page's asynchronous answers
#pragma once

#include <QHash>
#include <QSignalSpy>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTest>
#include <QTimer>
#include <QWebEnginePage>
#include <QWebEngineView>
#include <functional>
#include <memory>
#include <optional>

inline constexpr int asyncTimeout = 15000;

struct HttpReply {
    QByteArray body;
    QByteArray contentType = "text/html; charset=utf-8";
    int status = 200;
    QList<std::pair<QByteArray, QByteArray>> headers = {};
    int delayMs = 0;
};
Q_DECLARE_METATYPE(HttpReply)

// Serves fixed replies by path on 127.0.0.1, and remembers what was asked
class TestServer {
public:
    TestServer()
    {
        QObject::connect(&m_server, &QTcpServer::newConnection, &m_server, [this] {
            while (QTcpSocket* socket = m_server.nextPendingConnection())
                serve(socket);
        });
        if (!m_server.listen(QHostAddress::LocalHost))
            qFatal("TestServer: %s", qPrintable(m_server.errorString()));
    }

    void route(const QByteArray& path, const HttpReply& reply) { m_routes.insert(path, reply); }
    void route(const QByteArray& path, const QByteArray& html) { route(path, HttpReply { html }); }
    QUrl url(const QByteArray& path = "/") const
    {
        return QUrl(QStringLiteral("http://127.0.0.1:%1%2").arg(m_server.serverPort()).arg(QString::fromLatin1(path)));
    }
    // Paths requested so far, without their queries
    QList<QByteArray> requests() const { return m_requests; }
    int requestCount(const QByteArray& path) const { return m_requests.count(path); }
    // A header of the latest request for the path, lower-case name
    QByteArray requestHeader(const QByteArray& path, const QByteArray& name) const
    {
        return m_headers.value(path).value(name.toLower());
    }

private:
    void serve(QTcpSocket* socket)
    {
        auto received = std::make_shared<QByteArray>();
        QObject::connect(socket, &QTcpSocket::readyRead, socket, [this, socket, received] {
            received->append(socket->readAll());
            const qsizetype headerEnd = received->indexOf("\r\n\r\n");
            if (headerEnd < 0)
                return;
            const QList<QByteArray> lines = received->left(headerEnd).split('\n');
            const QByteArray path = lines.first().split(' ').value(1).split('?').first();
            QHash<QByteArray, QByteArray> headers;
            for (const QByteArray& line : lines.mid(1)) {
                const qsizetype colon = line.indexOf(':');
                headers.insert(line.left(colon).trimmed().toLower(), line.mid(colon + 1).trimmed());
            }
            m_requests.append(path);
            m_headers.insert(path, headers);
            received->clear();
            const HttpReply reply = m_routes.value(path, HttpReply { "not found", "text/plain", 404 });
            QTimer::singleShot(reply.delayMs, socket, [socket, reply] { respond(socket, reply); });
        });
    }

    static void respond(QTcpSocket* socket, const HttpReply& reply)
    {
        QByteArray response = "HTTP/1.1 " + QByteArray::number(reply.status) + " Status\r\nContent-Type: " + reply.contentType
            + "\r\nConnection: close\r\n";
        bool hasLength = false;
        for (const auto& [name, value] : reply.headers) {
            response += name + ": " + value + "\r\n";
            hasLength |= name.compare("Content-Length", Qt::CaseInsensitive) == 0;
        }
        if (!hasLength)
            response += "Content-Length: " + QByteArray::number(reply.body.size()) + "\r\n";
        socket->write(response + "\r\n" + reply.body);
        socket->disconnectFromHost();
    }

    QTcpServer m_server;
    QHash<QByteArray, HttpReply> m_routes;
    QList<QByteArray> m_requests;
    QHash<QByteArray, QHash<QByteArray, QByteArray>> m_headers;
};

// The script's result, or an invalid QVariant with a warning when no answer came
inline QVariant evaluate(QWebEnginePage* page, const QString& script, quint32 worldId = 0)
{
    auto result = std::make_shared<std::optional<QVariant>>();
    page->runJavaScript(script, worldId, [result](const QVariant& value) { *result = value; });
    if (!QTest::qWaitFor([&] { return result->has_value(); }, asyncTimeout))
        qWarning("No result from script: %s", qPrintable(script));
    return result->value_or(QVariant());
}

// Starts a load and reports whether it finished well
inline bool loadsOk(QWebEnginePage* page, const std::function<void()>& start)
{
    QSignalSpy finished(page, &QWebEnginePage::loadFinished);
    start();
    if (!finished.wait(asyncTimeout)) {
        qWarning("No loadFinished");
        return false;
    }
    return finished.first().first().toBool();
}

inline bool loadsOk(QWebEnginePage* page, const QUrl& url)
{
    return loadsOk(page, [&] { page->load(url); });
}

inline bool setsHtml(QWebEnginePage* page, const QString& html, const QUrl& baseUrl = {})
{
    return loadsOk(page, [&] { page->setHtml(html, baseUrl); });
}

// A shown view, so that its page is visible as in a browser
struct ShownView {
    explicit ShownView(QWebEnginePage* page = nullptr)
    {
        if (page) {
            page->setParent(&view);
            view.setPage(page);
        }
        view.resize(800, 600);
        view.show();
        if (!QTest::qWaitForWindowExposed(&view))
            qWarning("View not exposed");
    }
    QWebEnginePage* page() const { return view.page(); }

    QWebEngineView view;
};
