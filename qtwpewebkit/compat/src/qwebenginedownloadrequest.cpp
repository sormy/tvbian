#include "qwebenginedownloadrequest.h"

#include "internal.h"
#include "qwebengineprofile.h"

#include <QDir>
#include <wpe/webkit.h>

struct QWebEngineDownloadRequest::DownloadSignals {
    // Answered by accept() or cancel(), now or later
    static gboolean decideDestination(WebKitDownload*, char* suggestedFileName, QWebEngineDownloadRequest* request)
    {
        request->m_suggestedFileName = request->m_downloadFileName = QString::fromUtf8(suggestedFileName);
        Q_EMIT static_cast<QWebEngineProfile*>(request->parent())->downloadRequested(request);
        return TRUE;
    }

    static void failed(WebKitDownload*, GError* error, QWebEngineDownloadRequest* request)
    {
        if (request->isFinished())
            return;
        const bool canceled = g_error_matches(error, WEBKIT_DOWNLOAD_ERROR, WEBKIT_DOWNLOAD_ERROR_CANCELLED_BY_USER);
        request->m_interruptReason = canceled ? UserCanceled
            : g_error_matches(error, WEBKIT_DOWNLOAD_ERROR, WEBKIT_DOWNLOAD_ERROR_DESTINATION) ? FileFailed
                                                                                           : NetworkFailed;
        request->m_interruptReasonString = QString::fromUtf8(error->message);
        Q_EMIT request->interruptReasonChanged();
        request->setState(canceled ? DownloadCancelled : DownloadInterrupted);
    }

    // WebKit reports a failure, then the end
    static void finished(QWebEngineDownloadRequest* request)
    {
        if (!request->isFinished())
            request->setState(DownloadCompleted);
    }

    static void connect(QWebEngineDownloadRequest* request)
    {
        WebKitDownload* download = request->m_download;
        g_signal_connect(download, "decide-destination", G_CALLBACK(decideDestination), request);
        g_signal_connect(download, "failed", G_CALLBACK(failed), request);
        g_signal_connect_swapped(download, "finished", G_CALLBACK(finished), request);
        g_signal_connect_swapped(download, "received-data", G_CALLBACK(+[](QWebEngineDownloadRequest* request) {
            Q_EMIT request->receivedBytesChanged();
        }), request);
        g_signal_connect_swapped(download, "notify::response", G_CALLBACK(+[](QWebEngineDownloadRequest* request) {
            Q_EMIT request->totalBytesChanged();
        }), request);
    }
};

QWebEngineDownloadRequest::QWebEngineDownloadRequest(WebKitDownload* download, QWebEngineProfile* profile)
    : QObject(profile)
    , m_download(WEBKIT_DOWNLOAD(g_object_ref(download)))
    , m_downloadDirectory(profile->downloadPath())
{
    static quint32 lastId = 0;
    m_id = ++lastId;
    DownloadSignals::connect(this);
}

QWebEngineDownloadRequest::~QWebEngineDownloadRequest()
{
    if (m_state == DownloadRequested)
        webkit_download_cancel(m_download);
    g_signal_handlers_disconnect_by_data(m_download, this);
    g_object_unref(m_download);
}

qint64 QWebEngineDownloadRequest::totalBytes() const
{
    WebKitURIResponse* response = webkit_download_get_response(m_download);
    const guint64 length = response ? webkit_uri_response_get_content_length(response) : 0;
    return length ? qint64(length) : -1;
}

qint64 QWebEngineDownloadRequest::receivedBytes() const
{
    return webkit_download_get_received_data_length(m_download);
}

QUrl QWebEngineDownloadRequest::url() const
{
    return QUrl::fromEncoded(webkit_uri_request_get_uri(webkit_download_get_request(m_download)));
}

QString QWebEngineDownloadRequest::mimeType() const
{
    WebKitURIResponse* response = webkit_download_get_response(m_download);
    return response ? QString::fromUtf8(webkit_uri_response_get_mime_type(response)) : QString();
}

void QWebEngineDownloadRequest::setDownloadDirectory(const QString& directory)
{
    if (m_state != DownloadRequested || directory == m_downloadDirectory)
        return;
    m_downloadDirectory = directory;
    Q_EMIT downloadDirectoryChanged();
}

void QWebEngineDownloadRequest::setDownloadFileName(const QString& fileName)
{
    if (m_state != DownloadRequested || fileName == m_downloadFileName)
        return;
    m_downloadFileName = fileName;
    Q_EMIT downloadFileNameChanged();
}

bool QWebEngineDownloadRequest::isSavePageDownload() const
{
    return g_object_get_data(G_OBJECT(m_download), QtWpeWebKit::saveAsKey);
}

QWebEnginePage* QWebEngineDownloadRequest::page() const
{
    WebKitWebView* webView = webkit_download_get_web_view(m_download);
    return webView ? QtWpeWebKit::pageOf(webView) : nullptr;
}

void QWebEngineDownloadRequest::accept()
{
    if (m_state != DownloadRequested)
        return;
    const QString path = QDir(m_downloadDirectory).absoluteFilePath(m_downloadFileName);
    if (savePageFormat() == MimeHtmlSaveFormat) {
        saveAsMhtml(path);
        return;
    }
    setState(DownloadInProgress);
    webkit_download_set_destination(m_download, path.toUtf8().constData());
}

// Save Page archives the page as MHTML, as QtWebEngine does unless asked for its HTML
QWebEngineDownloadRequest::SavePageFormat QWebEngineDownloadRequest::savePageFormat() const
{
    return m_savePageFormat.value_or(isSavePageDownload() ? MimeHtmlSaveFormat : UnknownSaveFormat);
}

void QWebEngineDownloadRequest::setSavePageFormat(SavePageFormat format)
{
    if (m_state != DownloadRequested || !isSavePageDownload() || format == savePageFormat())
        return;
    m_savePageFormat = format;
    Q_EMIT savePageFormatChanged();
}

void QWebEngineDownloadRequest::saveAsMhtml(const QString& path)
{
    WebKitWebView* webView = webkit_download_get_web_view(m_download);
    g_signal_handlers_disconnect_by_data(m_download, this);
    webkit_download_cancel(m_download);
    setState(DownloadInProgress);
    g_autoptr(GFile) file = g_file_new_for_path(QFile::encodeName(path).constData());
    webkit_web_view_save_to_file(webView, file, WEBKIT_SAVE_MODE_MHTML, nullptr,
        [](GObject* view, GAsyncResult* result, gpointer data) {
            std::unique_ptr<QPointer<QWebEngineDownloadRequest>> request(static_cast<QPointer<QWebEngineDownloadRequest>*>(data));
            g_autoptr(GError) error = nullptr;
            const bool saved = webkit_web_view_save_to_file_finish(WEBKIT_WEB_VIEW(view), result, &error);
            if (!*request)
                return;
            if (!saved) {
                (*request)->m_interruptReason = FileFailed;
                (*request)->m_interruptReasonString = QString::fromUtf8(error->message);
                Q_EMIT (*request)->interruptReasonChanged();
            }
            (*request)->setState(saved ? DownloadCompleted : DownloadInterrupted);
        },
        new QPointer<QWebEngineDownloadRequest>(this));
}

// Cancelled at once, as in QtWebEngine; WebKit reports it later
void QWebEngineDownloadRequest::cancel()
{
    if (isFinished())
        return;
    webkit_download_cancel(m_download);
    if (isFinished())
        return;
    m_interruptReason = UserCanceled;
    Q_EMIT interruptReasonChanged();
    setState(DownloadCancelled);
}

void QWebEngineDownloadRequest::setState(DownloadState state)
{
    m_state = state;
    Q_EMIT stateChanged(state);
    if (isFinished())
        Q_EMIT isFinishedChanged();
}
