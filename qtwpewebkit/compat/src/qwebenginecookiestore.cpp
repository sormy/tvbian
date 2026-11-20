#include "qwebenginecookiestore.h"

#include "qwebengineprofile.h"

#include <QDir>
#include <QPointer>
#include <wpe/webkit.h>

static QNetworkCookie cookieOf(SoupCookie* soup)
{
    QNetworkCookie cookie(soup_cookie_get_name(soup), soup_cookie_get_value(soup));
    cookie.setDomain(QString::fromUtf8(soup_cookie_get_domain(soup)));
    cookie.setPath(QString::fromUtf8(soup_cookie_get_path(soup)));
    cookie.setSecure(soup_cookie_get_secure(soup));
    cookie.setHttpOnly(soup_cookie_get_http_only(soup));
    if (GDateTime* expires = soup_cookie_get_expires(soup))
        cookie.setExpirationDate(QDateTime::fromSecsSinceEpoch(g_date_time_to_unix(expires)));
    return cookie;
}

// Without a domain the cookie is the origin's
static SoupCookie* soupCookieOf(const QNetworkCookie& cookie, const QUrl& origin)
{
    const QString domain = cookie.domain().isEmpty() ? origin.host() : cookie.domain();
    const QString path = cookie.path().isEmpty() ? QStringLiteral("/") : cookie.path();
    SoupCookie* soup = soup_cookie_new(cookie.name().constData(), cookie.value().constData(), domain.toUtf8().constData(),
        path.toUtf8().constData(), -1);
    soup_cookie_set_secure(soup, cookie.isSecure());
    soup_cookie_set_http_only(soup, cookie.isHttpOnly());
    if (!cookie.isSessionCookie()) {
        g_autoptr(GDateTime) expires = g_date_time_new_from_unix_utc(cookie.expirationDate().toSecsSinceEpoch());
        soup_cookie_set_expires(soup, expires);
    }
    return soup;
}

static WebKitCookieManager* managerOf(WebKitNetworkSession* session)
{
    return webkit_network_session_get_cookie_manager(session);
}

QWebEngineCookieStore::QWebEngineCookieStore(WebKitNetworkSession* session, QWebEngineProfile* profile)
    : QObject(profile)
    , m_session(session)
{
    g_signal_connect_swapped(managerOf(session), "changed", G_CALLBACK(+[](QWebEngineCookieStore* store) {
        store->reportChanges();
    }), this);
}

QWebEngineCookieStore::~QWebEngineCookieStore()
{
    g_signal_handlers_disconnect_by_data(managerOf(m_session), this);
}

void QWebEngineCookieStore::setStorageDirectory(const QString& directory)
{
    const QByteArray path = QDir(directory).filePath(QStringLiteral("cookies.sqlite")).toUtf8();
    webkit_cookie_manager_set_persistent_storage(managerOf(m_session), path.constData(), WEBKIT_COOKIE_PERSISTENT_STORAGE_SQLITE);
    reportChanges();
}

void QWebEngineCookieStore::forEachCookie(const std::function<void(const QList<QNetworkCookie>&)>& callback)
{
    struct Call {
        QPointer<QWebEngineCookieStore> store;
        std::function<void(const QList<QNetworkCookie>&)> callback;
    };
    webkit_cookie_manager_get_all_cookies(managerOf(m_session), nullptr,
        [](GObject* manager, GAsyncResult* result, gpointer data) {
            std::unique_ptr<Call> call(static_cast<Call*>(data));
            GList* soupCookies = webkit_cookie_manager_get_all_cookies_finish(WEBKIT_COOKIE_MANAGER(manager), result, nullptr);
            QList<QNetworkCookie> cookies;
            for (GList* item = soupCookies; item; item = item->next)
                cookies.append(cookieOf(static_cast<SoupCookie*>(item->data)));
            g_list_free_full(soupCookies, reinterpret_cast<GDestroyNotify>(soup_cookie_free));
            if (call->store)
                call->callback(cookies);
        },
        new Call { this, callback });
}

// Each change fetches every cookie; the fetches can finish out of order, so only the latest's are reported
void QWebEngineCookieStore::reportChanges()
{
    forEachCookie([this, fetch = ++m_fetches](const QList<QNetworkCookie>& cookies) {
        if (fetch == m_fetches)
            update(cookies);
    });
}

void QWebEngineCookieStore::update(const QList<QNetworkCookie>& cookies)
{
    for (const QNetworkCookie& cookie : std::as_const(m_cookies)) {
        if (!cookies.contains(cookie))
            Q_EMIT cookieRemoved(cookie);
    }
    for (const QNetworkCookie& cookie : cookies) {
        if (!m_cookies.contains(cookie))
            Q_EMIT cookieAdded(cookie);
    }
    m_cookies = cookies;
}

// Cookies already reported are not reported again
void QWebEngineCookieStore::loadAllCookies()
{
    reportChanges();
}

void QWebEngineCookieStore::setCookie(const QNetworkCookie& cookie, const QUrl& origin)
{
    SoupCookie* soup = soupCookieOf(cookie, origin);
    webkit_cookie_manager_add_cookie(managerOf(m_session), soup, nullptr, nullptr, nullptr);
    soup_cookie_free(soup);
}

void QWebEngineCookieStore::deleteCookie(const QNetworkCookie& cookie, const QUrl& origin)
{
    SoupCookie* soup = soupCookieOf(cookie, origin);
    webkit_cookie_manager_delete_cookie(managerOf(m_session), soup, nullptr, nullptr, nullptr);
    soup_cookie_free(soup);
}

void QWebEngineCookieStore::deleteSessionCookies()
{
    forEachCookie([this](const QList<QNetworkCookie>& cookies) {
        for (const QNetworkCookie& cookie : cookies) {
            if (cookie.isSessionCookie())
                deleteCookie(cookie);
        }
    });
}

void QWebEngineCookieStore::deleteAllCookies()
{
    webkit_website_data_manager_clear(webkit_network_session_get_website_data_manager(m_session),
        WEBKIT_WEBSITE_DATA_COOKIES, 0, nullptr, nullptr, nullptr);
}
