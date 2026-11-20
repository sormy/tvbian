// One request to a custom scheme, answered from a QIODevice
#pragma once

#include <QMap>
#include <QObject>
#include <QUrl>

class QIODevice;
typedef struct _WebKitURISchemeRequest WebKitURISchemeRequest;

class QWebEngineUrlRequestJob : public QObject {
    Q_OBJECT
public:
    enum Error { NoError = 0, UrlNotFound, UrlInvalid, RequestAborted, RequestDenied, RequestFailed };

    explicit QWebEngineUrlRequestJob(WebKitURISchemeRequest* request);
    ~QWebEngineUrlRequestJob() override;

    QUrl requestUrl() const;
    QByteArray requestMethod() const;
    QUrl initiator() const { return {}; }
    QMap<QByteArray, QByteArray> requestHeaders() const { return {}; }
    // Reads what the device has now; QtWebEngine would also wait for more
    void reply(const QByteArray& contentType, QIODevice* device);
    void fail(Error error);
    void redirect(const QUrl& url);

private:
    void finish(const QByteArray& contentType, const QByteArray& data);

    WebKitURISchemeRequest* m_request;
};
