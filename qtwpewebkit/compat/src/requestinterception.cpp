#include "requestinterception.h"

#include "qwebenginepage.h"
#include "qwebengineprofile.h"
#include "qwebengineurlrequestinfo.h"
#include "requestprotocol.h"

#include <QFile>
#include <QFileInfo>
#include <QLocalServer>
#include <QLocalSocket>
#include <QStandardPaths>
#include <dlfcn.h>
#include <wpe/webkit.h>

using ResourceType = QWebEngineUrlRequestInfo::ResourceType;

namespace QtWpeWebKit {

// Beside libqtwpewebkit, in the build tree as when installed
static QByteArray extensionsDirectory()
{
    Dl_info library;
    dladdr(reinterpret_cast<const void*>(&extensionsDirectory), &library);
    return QFile::encodeName(QFileInfo(QFile::decodeName(library.dli_fname)).absolutePath()) + "/qtwpewebkit/web-process-extensions";
}

static ResourceType resourceTypeOf(const QByteArray& fetchDestination, const QByteArray& accept, bool isPageUrl)
{
    static const QHash<QByteArray, ResourceType> destinations {
        { "document", QWebEngineUrlRequestInfo::ResourceTypeMainFrame },
        { "iframe", QWebEngineUrlRequestInfo::ResourceTypeSubFrame },
        { "frame", QWebEngineUrlRequestInfo::ResourceTypeSubFrame },
        { "script", QWebEngineUrlRequestInfo::ResourceTypeScript },
        { "style", QWebEngineUrlRequestInfo::ResourceTypeStylesheet },
        { "image", QWebEngineUrlRequestInfo::ResourceTypeImage },
        { "font", QWebEngineUrlRequestInfo::ResourceTypeFontResource },
        { "audio", QWebEngineUrlRequestInfo::ResourceTypeMedia },
        { "video", QWebEngineUrlRequestInfo::ResourceTypeMedia },
        { "track", QWebEngineUrlRequestInfo::ResourceTypeMedia },
        { "object", QWebEngineUrlRequestInfo::ResourceTypeObject },
        { "embed", QWebEngineUrlRequestInfo::ResourceTypeObject },
        { "worker", QWebEngineUrlRequestInfo::ResourceTypeWorker },
        { "sharedworker", QWebEngineUrlRequestInfo::ResourceTypeSharedWorker },
        { "serviceworker", QWebEngineUrlRequestInfo::ResourceTypeServiceWorker },
        { "report", QWebEngineUrlRequestInfo::ResourceTypeCspReport },
        { "manifest", QWebEngineUrlRequestInfo::ResourceTypeSubResource },
        { "empty", QWebEngineUrlRequestInfo::ResourceTypeXhr },
    };
    if (!fetchDestination.isEmpty())
        return destinations.value(fetchDestination, QWebEngineUrlRequestInfo::ResourceTypeUnknown);
    // WebKit sends fetch metadata to secure origins only; its Accept header still tells documents, images and style sheets
    if (accept.startsWith("text/html"))
        return isPageUrl ? QWebEngineUrlRequestInfo::ResourceTypeMainFrame : QWebEngineUrlRequestInfo::ResourceTypeSubFrame;
    if (accept.startsWith("image/"))
        return QWebEngineUrlRequestInfo::ResourceTypeImage;
    if (accept.startsWith("text/css"))
        return QWebEngineUrlRequestInfo::ResourceTypeStylesheet;
    return QWebEngineUrlRequestInfo::ResourceTypeUnknown;
}

RequestInterception& RequestInterception::instance()
{
    static auto* interception = new RequestInterception;
    return *interception;
}

RequestInterception::RequestInterception()
    : m_serverDirectory(QStandardPaths::writableLocation(QStandardPaths::RuntimeLocation) + QLatin1String("/qtwpewebkit-XXXXXX"))
    , m_server(new QLocalServer)
{
    m_server->setSocketOptions(QLocalServer::UserAccessOption);
    if (!m_server->listen(m_serverDirectory.filePath(QStringLiteral("requests"))))
        qWarning("QtWpeWebKit: no request interception: %s", qPrintable(m_server->errorString()));
    connect(m_server, &QLocalServer::newConnection, m_server, [this] {
        while (QLocalSocket* socket = m_server->nextPendingConnection())
            serve(socket);
    });
    m_server->moveToThread(&m_thread);
    m_thread.start();

    WebKitWebContext* context = webkit_web_context_get_default();
    // Sandboxed web processes see a /tmp and a runtime directory of their own
    webkit_web_context_add_path_to_sandbox(context, QFile::encodeName(m_serverDirectory.path()).constData(), TRUE);
    webkit_web_context_set_web_process_extensions_directory(context, extensionsDirectory().constData());
    webkit_web_context_set_web_process_extensions_initialization_user_data(context,
        g_variant_new_string(QFile::encodeName(m_server->fullServerName()).constData()));
}

void RequestInterception::addPage(QWebEnginePage* page)
{
    removePage(page);
    m_pages.insert(webkit_web_view_get_page_id(page->webKitWebView()), page);
}

void RequestInterception::removePage(QWebEnginePage* page)
{
    m_pages.removeIf([page](auto entry) { return entry.value() == page; });
}

// A web process sends one request at a time and waits for its answer
void RequestInterception::serve(QLocalSocket* socket)
{
    connect(socket, &QLocalSocket::disconnected, socket, &QObject::deleteLater);
    connect(socket, &QLocalSocket::readyRead, socket, [this, socket] {
        quint32 size;
        while (socket->peek(reinterpret_cast<char*>(&size), sizeof size) == sizeof size
            && socket->bytesAvailable() >= qint64(sizeof size + size)) {
            socket->skip(sizeof size);
            const QByteArray reply = answer(socket->read(size));
            const quint32 replySize = reply.size();
            socket->write(reinterpret_cast<const char*>(&replySize), sizeof replySize);
            socket->write(reply);
        }
    });
}

QByteArray RequestInterception::answer(const QByteArray& message)
{
    g_autoptr(GBytes) bytes = g_bytes_new(message.constData(), message.size());
    g_autoptr(GVariant) request = g_variant_ref_sink(g_variant_new_from_bytes(G_VARIANT_TYPE(requestFormat), bytes, FALSE));
    guint64 pageId;
    const char *url, *pageUrl, *method, *fetchDestination, *accept;
    g_variant_get(request, "(t&s&s&s&s&s)", &pageId, &url, &pageUrl, &method, &fetchDestination, &accept);

    const QUrl requestUrl = QUrl::fromEncoded(url);
    const ResourceType type = resourceTypeOf(fetchDestination, accept, qstrcmp(url, pageUrl) == 0);
    const bool isFrame = type == QWebEngineUrlRequestInfo::ResourceTypeMainFrame || type == QWebEngineUrlRequestInfo::ResourceTypeSubFrame;
    const QUrl firstPartyUrl = type == QWebEngineUrlRequestInfo::ResourceTypeMainFrame ? requestUrl : QUrl::fromEncoded(pageUrl);
    QWebEngineUrlRequestInfo info(type, QWebEngineUrlRequestInfo::NavigationTypeOther, requestUrl, firstPartyUrl, method);
    QMetaObject::invokeMethod(this, [&] {
        QWebEnginePage* page = m_pages.value(pageId);
        if (!page)
            return;
        // The page's and the request's navigation types list the same kinds in the same order
        if (isFrame)
            info.m_navigationType = static_cast<QWebEngineUrlRequestInfo::NavigationType>(page->m_navigationType);
        for (QWebEngineUrlRequestInterceptor* interceptor : { page->profile()->urlRequestInterceptor(), page->urlRequestInterceptor() })
            if (interceptor)
                interceptor->interceptRequest(info);
        if (info.m_blocked && type == QWebEngineUrlRequestInfo::ResourceTypeMainFrame)
            page->m_mainFrameBlocked = true;
    }, Qt::BlockingQueuedConnection);

    GVariantBuilder headers;
    g_variant_builder_init(&headers, G_VARIANT_TYPE("a{ss}"));
    for (auto header = info.m_httpHeaders.cbegin(); header != info.m_httpHeaders.cend(); ++header)
        g_variant_builder_add(&headers, "{ss}", header.key().constData(), header.value().constData());
    g_autoptr(GVariant) reply = g_variant_ref_sink(
        g_variant_new(replyFormat, gboolean(info.m_blocked), info.m_redirectUrl.toEncoded().constData(), &headers));
    return QByteArray(static_cast<const char*>(g_variant_get_data(reply)), g_variant_get_size(reply));
}

} // namespace QtWpeWebKit
