// A browsing profile: a WebKitNetworkSession plus the settings and user scripts its pages share
#pragma once

#include "qwebengineurlrequestinfo.h"

#include <QHash>
#include <QObject>
#include <QPointer>
#include <QScopedPointer>
#include <QStringList>
#include <functional>
#include <memory>

namespace QtWpeWebKit {
class ContentFilter;
}
class QWebEngineCookieStore;
class QWebEngineDownloadRequest;
class QWebEngineNotification;
class QWebEngineScriptCollection;
class QWebEngineSettings;
class QWebEngineUrlSchemeHandler;
typedef struct _WebKitNetworkSession WebKitNetworkSession;
typedef struct _WebKitURISchemeRequest WebKitURISchemeRequest;

class QWebEngineProfile : public QObject {
    Q_OBJECT
public:
    enum HttpCacheType { MemoryHttpCache, DiskHttpCache, NoCache };
    enum PersistentCookiesPolicy { NoPersistentCookies, AllowPersistentCookies, ForcePersistentCookies };

    // Off the record
    explicit QWebEngineProfile(QObject* parent = nullptr);
    // Stored under the application's data and cache directories
    explicit QWebEngineProfile(const QString& storageName, QObject* parent = nullptr);
    ~QWebEngineProfile() override;

    static QWebEngineProfile* defaultProfile();

    QString storageName() const { return m_storageName; }
    bool isOffTheRecord() const { return m_storageName.isEmpty(); }
    QString persistentStoragePath() const { return m_storagePath; }
    // WebKit keeps its other data where the profile was made
    void setPersistentStoragePath(const QString& path);
    QString cachePath() const { return m_cachePath; }
    void setCachePath(const QString& path) { m_cachePath = path; }
    QString downloadPath() const { return m_downloadPath; }
    void setDownloadPath(const QString& path) { m_downloadPath = path; }
    QString httpUserAgent() const;
    void setHttpUserAgent(const QString& userAgent);
    QString httpAcceptLanguage() const { return m_acceptLanguage; }
    void setHttpAcceptLanguage(const QString& language) { m_acceptLanguage = language; }
    HttpCacheType httpCacheType() const { return m_httpCacheType; }
    void setHttpCacheType(HttpCacheType type) { m_httpCacheType = type; }
    PersistentCookiesPolicy persistentCookiesPolicy() const { return m_cookiesPolicy; }
    void setPersistentCookiesPolicy(PersistentCookiesPolicy policy) { m_cookiesPolicy = policy; }
    int httpCacheMaximumSize() const { return m_httpCacheMaximumSize; }
    void setHttpCacheMaximumSize(int size) { m_httpCacheMaximumSize = size; }
    void clearHttpCache() { }
    void clearAllVisitedLinks() { }
    void clearVisitedLinks(const QList<QUrl>&) { }
    bool visitedLinksContainsUrl(const QUrl&) const { return false; }
    void setSpellCheckEnabled(bool enabled);
    bool isSpellCheckEnabled() const { return m_spellCheckEnabled; }
    void setSpellCheckLanguages(const QStringList& languages);
    QStringList spellCheckLanguages() const { return m_spellCheckLanguages; }
    void setUrlRequestInterceptor(QWebEngineUrlRequestInterceptor* interceptor) { m_requestInterceptor = interceptor; }
    QWebEngineUrlRequestInterceptor* urlRequestInterceptor() const { return m_requestInterceptor; }
    void setNotificationPresenter(std::function<void(std::unique_ptr<QWebEngineNotification>)>) { }

    QWebEngineSettings* settings() const { return m_settings.get(); }
    QWebEngineScriptCollection* scripts() const { return m_scripts.get(); }
    QWebEngineCookieStore* cookieStore() const { return m_cookieStore; }

    const QWebEngineUrlSchemeHandler* urlSchemeHandler(const QByteArray& scheme) const { return m_schemeHandlers.value(scheme); }
    void installUrlSchemeHandler(const QByteArray& scheme, QWebEngineUrlSchemeHandler* handler);
    void removeUrlScheme(const QByteArray& scheme) { m_schemeHandlers.remove(scheme); }
    void removeUrlSchemeHandler(QWebEngineUrlSchemeHandler* handler);
    void removeAllUrlSchemeHandlers() { m_schemeHandlers.clear(); }

    WebKitNetworkSession* networkSession() const { return m_networkSession; }
    // QtWpeWebKit's: Adblock Plus filter lists, for WebKit's content blockers to apply far faster than an interceptor; empty for none
    void setAdblockFilters(const QString& filterLists);

Q_SIGNALS:
    void downloadRequested(QWebEngineDownloadRequest* download);

private:
    friend class QWebEnginePage;
    static void registerSchemeInWebKit(const QByteArray& scheme);
    static void startUrlRequest(WebKitURISchemeRequest* request);

    QString m_storageName;
    QString m_storagePath;
    QString m_cachePath;
    QString m_downloadPath;
    QString m_acceptLanguage;
    HttpCacheType m_httpCacheType = DiskHttpCache;
    PersistentCookiesPolicy m_cookiesPolicy = AllowPersistentCookies;
    int m_httpCacheMaximumSize = 0;
    bool m_spellCheckEnabled = false;
    QStringList m_spellCheckLanguages;
    WebKitNetworkSession* m_networkSession;
    std::unique_ptr<QWebEngineSettings> m_settings;
    std::unique_ptr<QWebEngineScriptCollection> m_scripts;
    QWebEngineCookieStore* m_cookieStore;
    QHash<QByteArray, QWebEngineUrlSchemeHandler*> m_schemeHandlers;
    QPointer<QWebEngineUrlRequestInterceptor> m_requestInterceptor;
    QtWpeWebKit::ContentFilter* m_contentFilter;
};
