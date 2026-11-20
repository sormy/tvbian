// Request interception: each request of a page waits in its web process for the interceptors' answer (docs/interception.md)
#pragma once

#include <QHash>
#include <QObject>
#include <QUrl>

namespace QtWpeWebKit {
class RequestInterception;
}

class QWebEngineUrlRequestInfo {
public:
    enum ResourceType {
        ResourceTypeMainFrame = 0,
        ResourceTypeSubFrame,
        ResourceTypeStylesheet,
        ResourceTypeScript,
        ResourceTypeImage,
        ResourceTypeFontResource,
        ResourceTypeSubResource,
        ResourceTypeObject,
        ResourceTypeMedia,
        ResourceTypeWorker,
        ResourceTypeSharedWorker,
        ResourceTypePrefetch,
        ResourceTypeFavicon,
        ResourceTypeXhr,
        ResourceTypePing,
        ResourceTypeServiceWorker,
        ResourceTypeCspReport,
        ResourceTypePluginResource,
        ResourceTypeNavigationPreloadMainFrame = 19,
        ResourceTypeNavigationPreloadSubFrame,
        ResourceTypeWebSocket = 254,
        ResourceTypeUnknown = 255,
    };
    enum NavigationType {
        NavigationTypeLink,
        NavigationTypeTyped,
        NavigationTypeFormSubmitted,
        NavigationTypeBackForward,
        NavigationTypeReload,
        NavigationTypeOther,
        NavigationTypeRedirect,
    };

    ResourceType resourceType() const { return m_resourceType; }
    NavigationType navigationType() const { return m_navigationType; }
    QUrl requestUrl() const { return m_requestUrl; }
    QUrl firstPartyUrl() const { return m_firstPartyUrl; }
    QUrl initiator() const { return {}; }
    QByteArray requestMethod() const { return m_requestMethod; }
    bool changed() const { return m_changed; }
    void block(bool shouldBlock)
    {
        m_blocked = shouldBlock;
        m_changed = true;
    }
    void redirect(const QUrl& url)
    {
        m_redirectUrl = url;
        m_changed = true;
    }
    void setHttpHeader(const QByteArray& name, const QByteArray& value)
    {
        m_httpHeaders.insert(name, value);
        m_changed = true;
    }
    // Only those set here: WebKit adds the rest later
    QHash<QByteArray, QByteArray> httpHeaders() const { return m_httpHeaders; }
    bool isDownload() const { return false; }

private:
    friend class QtWpeWebKit::RequestInterception;
    QWebEngineUrlRequestInfo(ResourceType resourceType, NavigationType navigationType, const QUrl& requestUrl,
        const QUrl& firstPartyUrl, const QByteArray& requestMethod)
        : m_resourceType(resourceType)
        , m_navigationType(navigationType)
        , m_requestUrl(requestUrl)
        , m_firstPartyUrl(firstPartyUrl)
        , m_requestMethod(requestMethod)
    {
    }

    ResourceType m_resourceType;
    NavigationType m_navigationType;
    QUrl m_requestUrl;
    QUrl m_firstPartyUrl;
    QByteArray m_requestMethod;
    bool m_changed = false;
    bool m_blocked = false;
    QUrl m_redirectUrl;
    QHash<QByteArray, QByteArray> m_httpHeaders;
};

class QWebEngineUrlRequestInterceptor : public QObject {
    Q_OBJECT
public:
    explicit QWebEngineUrlRequestInterceptor(QObject* parent = nullptr)
        : QObject(parent)
    {
    }
    // Called on a thread of QtWpeWebKit's, as QtWebEngine 5 called it on its IO thread: must be thread-safe
    virtual void interceptRequest(QWebEngineUrlRequestInfo& info) = 0;
};
