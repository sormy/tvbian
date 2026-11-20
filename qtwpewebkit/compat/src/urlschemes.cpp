// Custom schemes: registration, handlers and their requests
#include "internal.h"
#include "qwebenginepage.h"
#include "qwebengineprofile.h"
#include "qwebengineurlrequestjob.h"
#include "qwebengineurlscheme.h"
#include "qwebengineurlschemehandler.h"

#include <QDir>
#include <QFile>
#include <QHash>
#include <QMimeDatabase>
#include <QSet>
#include <wpe/webkit.h>

static QHash<QByteArray, QWebEngineUrlScheme>& registeredSchemes()
{
    static QHash<QByteArray, QWebEngineUrlScheme> schemes;
    return schemes;
}

void QWebEngineUrlScheme::registerScheme(const QWebEngineUrlScheme& scheme)
{
    registeredSchemes().insert(scheme.name(), scheme);
    auto* security = webkit_web_context_get_security_manager(webkit_web_context_get_default());
    const QByteArray name = scheme.name();
    if (scheme.flags() & SecureScheme)
        webkit_security_manager_register_uri_scheme_as_secure(security, name.constData());
    if (scheme.flags() & LocalScheme)
        webkit_security_manager_register_uri_scheme_as_local(security, name.constData());
    if (scheme.flags() & (CorsEnabled | FetchApiAllowed))
        webkit_security_manager_register_uri_scheme_as_cors_enabled(security, name.constData());
}

QWebEngineUrlScheme QWebEngineUrlScheme::schemeByName(const QByteArray& name)
{
    return registeredSchemes().value(name);
}

// WebKit takes a scheme once per context: the profile of the requesting page picks the handler
void QWebEngineProfile::installUrlSchemeHandler(const QByteArray& scheme, QWebEngineUrlSchemeHandler* handler)
{
    m_schemeHandlers.insert(scheme, handler);
    connect(handler, &QObject::destroyed, this, [this, handler] { removeUrlSchemeHandler(handler); });
    registerSchemeInWebKit(scheme);
}

void QWebEngineProfile::registerSchemeInWebKit(const QByteArray& scheme)
{
    static QSet<QByteArray> schemesInWebKit;
    if (schemesInWebKit.contains(scheme))
        return;
    schemesInWebKit.insert(scheme);
    webkit_web_context_register_uri_scheme(webkit_web_context_get_default(), scheme.constData(),
        [](WebKitURISchemeRequest* request, gpointer) { startUrlRequest(request); }, nullptr, nullptr);
}

// QtWebEngine serves the application's resources itself
static void replyWithResource(QWebEngineUrlRequestJob* job)
{
    auto* file = new QFile(QDir::cleanPath(QLatin1String(":/") + job->requestUrl().path()), job);
    if (file->open(QIODevice::ReadOnly))
        job->reply(QMimeDatabase().mimeTypeForFile(file->fileName()).name().toUtf8(), file);
    else
        job->fail(QWebEngineUrlRequestJob::UrlNotFound);
}

void QWebEngineProfile::startUrlRequest(WebKitURISchemeRequest* request)
{
    auto* job = new QWebEngineUrlRequestJob(request);
    QWebEnginePage* page = QtWpeWebKit::pageOf(webkit_uri_scheme_request_get_web_view(request));
    const QByteArray scheme = webkit_uri_scheme_request_get_scheme(request);
    if (auto* handler = page ? page->profile()->m_schemeHandlers.value(scheme) : nullptr)
        handler->requestStarted(job);
    else if (scheme == QtWpeWebKit::resourceScheme)
        replyWithResource(job);
    else
        job->fail(QWebEngineUrlRequestJob::UrlNotFound);
}

QWebEngineUrlRequestJob::QWebEngineUrlRequestJob(WebKitURISchemeRequest* request)
    : m_request(WEBKIT_URI_SCHEME_REQUEST(g_object_ref(request)))
{
}

QWebEngineUrlRequestJob::~QWebEngineUrlRequestJob()
{
    g_object_unref(m_request);
}

QUrl QWebEngineUrlRequestJob::requestUrl() const
{
    return QUrl::fromEncoded(webkit_uri_scheme_request_get_uri(m_request));
}

QByteArray QWebEngineUrlRequestJob::requestMethod() const
{
    return webkit_uri_scheme_request_get_http_method(m_request);
}

void QWebEngineUrlRequestJob::reply(const QByteArray& contentType, QIODevice* device)
{
    if (!device->isOpen())
        device->open(QIODevice::ReadOnly);
    finish(contentType, device->readAll());
}

void QWebEngineUrlRequestJob::fail(Error error)
{
    g_autoptr(GError) failure = g_error_new(WEBKIT_NETWORK_ERROR, WEBKIT_NETWORK_ERROR_FAILED, "Request failed (%d)", error);
    webkit_uri_scheme_request_finish_error(m_request, failure);
    deleteLater();
}

// WebKit's scheme requests cannot redirect: the page's own request becomes a load of the new URL,
// a frame's a page that navigates
void QWebEngineUrlRequestJob::redirect(const QUrl& url)
{
    WebKitWebView* webView = webkit_uri_scheme_request_get_web_view(m_request);
    QWebEnginePage* page = webView ? QtWpeWebKit::pageOf(webView) : nullptr;
    if (!page || !page->isLoading() || page->url() != requestUrl()) {
        finish("text/html", "<meta http-equiv=\"refresh\" content=\"0; url=" + url.toEncoded() + "\">");
        return;
    }
    page->redirectLoad(url);
    fail(RequestAborted);
}

void QWebEngineUrlRequestJob::finish(const QByteArray& contentType, const QByteArray& data)
{
    g_autoptr(GBytes) bytes = g_bytes_new(data.constData(), data.size());
    g_autoptr(GInputStream) stream = g_memory_input_stream_new_from_bytes(bytes);
    webkit_uri_scheme_request_finish(m_request, stream, data.size(), contentType.constData());
    deleteLater();
}
