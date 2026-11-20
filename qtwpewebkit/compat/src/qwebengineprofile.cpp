#include "qwebengineprofile.h"

#include "contentfilter.h"
#include "internal.h"
#include "qwebenginecookiestore.h"
#include "qwebenginedownloadrequest.h"
#include "qwebenginescriptcollection.h"
#include "qwebenginesettings.h"
#include "qwebengineurlschemehandler.h"
#include "requestinterception.h"

#include <QStandardPaths>
#include <wpe/webkit.h>

static QString storageDirectory(QStandardPaths::StandardLocation location, const QString& storageName)
{
    return storageName.isEmpty() ? QString()
                                 : QStandardPaths::writableLocation(location) + QLatin1String("/QtWebEngine/") + storageName;
}

QWebEngineProfile::QWebEngineProfile(QObject* parent)
    : QWebEngineProfile(QString(), parent)
{
}

QWebEngineProfile::QWebEngineProfile(const QString& storageName, QObject* parent)
    : QObject(parent)
    , m_storageName(storageName)
    , m_storagePath(storageDirectory(QStandardPaths::AppDataLocation, storageName))
    , m_cachePath(storageDirectory(QStandardPaths::CacheLocation, storageName))
    , m_downloadPath(QStandardPaths::writableLocation(QStandardPaths::DownloadLocation))
    , m_networkSession(isOffTheRecord()
              ? webkit_network_session_new_ephemeral()
              : webkit_network_session_new(m_storagePath.toUtf8().constData(), m_cachePath.toUtf8().constData()))
    , m_settings(std::make_unique<QWebEngineSettings>())
    , m_scripts(std::make_unique<QWebEngineScriptCollection>())
    , m_cookieStore(new QWebEngineCookieStore(m_networkSession, this))
    , m_contentFilter(new QtWpeWebKit::ContentFilter(this))
{
    QtWpeWebKit::RequestInterception::instance();
    registerSchemeInWebKit(QtWpeWebKit::resourceScheme);
    if (!isOffTheRecord())
        m_cookieStore->setStorageDirectory(m_storagePath);
    g_signal_connect(m_networkSession, "download-started", G_CALLBACK(+[](WebKitNetworkSession*, WebKitDownload* download, QWebEngineProfile* profile) {
        new QWebEngineDownloadRequest(download, profile);
    }), this);
}

QWebEngineProfile::~QWebEngineProfile()
{
    g_signal_handlers_disconnect_by_data(m_networkSession, this);
    g_object_unref(m_networkSession);
}

void QWebEngineProfile::setPersistentStoragePath(const QString& path)
{
    m_storagePath = path;
    if (!isOffTheRecord())
        m_cookieStore->setStorageDirectory(path);
}

QWebEngineProfile* QWebEngineProfile::defaultProfile()
{
    static auto* profile = new QWebEngineProfile;
    return profile;
}

QString QWebEngineProfile::httpUserAgent() const
{
    return QString::fromUtf8(webkit_settings_get_user_agent(m_settings->webKitSettings()));
}

void QWebEngineProfile::setHttpUserAgent(const QString& userAgent)
{
    m_settings->setUserAgent(userAgent);
}

void QWebEngineProfile::setAdblockFilters(const QString& filterLists)
{
    m_contentFilter->setAdblockFilters(filterLists);
}

void QWebEngineProfile::removeUrlSchemeHandler(QWebEngineUrlSchemeHandler* handler)
{
    m_schemeHandlers.removeIf([handler](auto entry) { return entry.value() == handler; });
}

// WebKit spellchecks for the whole process, as QtWebEngine does for its profile
void QWebEngineProfile::setSpellCheckEnabled(bool enabled)
{
    m_spellCheckEnabled = enabled;
    webkit_web_context_set_spell_checking_enabled(webkit_web_context_get_default(), enabled);
}

// QtWebEngine names a dictionary en-US; Enchant, under WebKit, en_US
void QWebEngineProfile::setSpellCheckLanguages(const QStringList& languages)
{
    m_spellCheckLanguages = languages;
    QList<QByteArray> names;
    for (const QString& language : languages)
        names.append(language.toUtf8().replace('-', '_'));
    std::vector<const char*> list;
    for (const QByteArray& name : names)
        list.push_back(name.constData());
    list.push_back(nullptr);
    webkit_web_context_set_spell_checking_languages(webkit_web_context_get_default(), list.data());
}
