// The profile's cookies, kept by WebKitCookieManager; changes are found by comparing WebKit's cookies with the last seen
#pragma once

#include <QNetworkCookie>
#include <QObject>
#include <QUrl>
#include <functional>

class QWebEngineProfile;
typedef struct _WebKitNetworkSession WebKitNetworkSession;

class QWebEngineCookieStore : public QObject {
    Q_OBJECT
public:
    struct FilterRequest {
        QUrl firstPartyUrl;
        QUrl origin;
        bool thirdParty;
        bool _reservedFlag;
        ushort _reservedType;
    };

    ~QWebEngineCookieStore() override;

    // WebKit asks no filter: its own policy decides on third-party cookies
    void setCookieFilter(std::function<bool(const FilterRequest&)>) { }
    void setCookie(const QNetworkCookie& cookie, const QUrl& origin = {});
    void deleteCookie(const QNetworkCookie& cookie, const QUrl& origin = {});
    void deleteSessionCookies();
    void deleteAllCookies();
    void loadAllCookies();

Q_SIGNALS:
    void cookieAdded(const QNetworkCookie& cookie);
    void cookieRemoved(const QNetworkCookie& cookie);

private:
    friend class QWebEngineProfile;
    QWebEngineCookieStore(WebKitNetworkSession* session, QWebEngineProfile* profile);
    void setStorageDirectory(const QString& directory);
    void forEachCookie(const std::function<void(const QList<QNetworkCookie>&)>& callback);
    // Reports what changed since the cookies seen last
    void reportChanges();
    void update(const QList<QNetworkCookie>& cookies);

    WebKitNetworkSession* m_session;
    QList<QNetworkCookie> m_cookies;
    quint64 m_fetches = 0;
};
