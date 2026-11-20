#include "contentfilter.h"

#include "adblockfilters.h"

#include <QCryptographicHash>
#include <QFile>
#include <QPointer>
#include <QStandardPaths>
#include <QThread>
#include <memory>
#include <wpe/webkit.h>

namespace QtWpeWebKit {

static const char identifierPrefix[] = "adblock-";

namespace {
struct Compilation {
    QPointer<ContentFilter> filter;
    QString identifier;
    QString filterLists;
};
}

ContentFilter::ContentFilter(QObject* parent)
    : QObject(parent)
    , m_store(webkit_user_content_filter_store_new(QFile::encodeName(
          QStandardPaths::writableLocation(QStandardPaths::CacheLocation) + QLatin1String("/qtwpewebkit-content-filters")).constData()))
{
}

ContentFilter::~ContentFilter()
{
    if (m_filter)
        webkit_user_content_filter_unref(m_filter);
    g_object_unref(m_store);
}

void ContentFilter::setAdblockFilters(const QString& filterLists)
{
    if (filterLists.isEmpty()) {
        m_identifier.clear();
        apply(nullptr);
        return;
    }
    const QString identifier = QLatin1String(identifierPrefix)
        + QString::fromLatin1(QCryptographicHash::hash(filterLists.toUtf8(), QCryptographicHash::Sha1).toHex());
    if (identifier == m_identifier)
        return;
    m_identifier = identifier;
    webkit_user_content_filter_store_load(m_store, identifier.toUtf8().constData(), nullptr,
        [](GObject* store, GAsyncResult* result, gpointer data) {
            std::unique_ptr<Compilation> compilation(static_cast<Compilation*>(data));
            WebKitUserContentFilter* filter = webkit_user_content_filter_store_load_finish(WEBKIT_USER_CONTENT_FILTER_STORE(store), result, nullptr);
            ContentFilter* self = compilation->filter;
            if (self && compilation->identifier == self->m_identifier)
                filter ? self->apply(filter) : self->compile(compilation->filterLists);
            if (filter)
                webkit_user_content_filter_unref(filter);
        },
        new Compilation { this, identifier, filterLists });
}

// Converting takes seconds on a small machine, WebKit compiles in the background itself
void ContentFilter::compile(const QString& filterLists)
{
    auto rules = std::make_shared<QByteArray>();
    QThread* conversion = QThread::create([rules, filterLists] { *rules = contentBlockerRules(filterLists); });
    connect(conversion, &QThread::finished, this, [this, rules, identifier = m_identifier] {
        if (identifier == m_identifier)
            save(*rules);
    });
    connect(conversion, &QThread::finished, conversion, &QObject::deleteLater);
    conversion->start();
}

void ContentFilter::save(const QByteArray& rules)
{
    g_autoptr(GBytes) bytes = g_bytes_new(rules.constData(), rules.size());
    webkit_user_content_filter_store_save(m_store, m_identifier.toUtf8().constData(), bytes, nullptr,
        [](GObject* store, GAsyncResult* result, gpointer data) {
            std::unique_ptr<Compilation> compilation(static_cast<Compilation*>(data));
            g_autoptr(GError) error = nullptr;
            WebKitUserContentFilter* filter = webkit_user_content_filter_store_save_finish(WEBKIT_USER_CONTENT_FILTER_STORE(store), result, &error);
            if (!filter) {
                qWarning("QtWpeWebKit: Adblock filters not compiled: %s", error->message);
                return;
            }
            ContentFilter* self = compilation->filter;
            if (self && compilation->identifier == self->m_identifier)
                self->apply(filter);
            webkit_user_content_filter_unref(filter);
            // Each compiled list takes megabytes: keep the latest only
            webkit_user_content_filter_store_fetch_identifiers(WEBKIT_USER_CONTENT_FILTER_STORE(store), nullptr,
                [](GObject* store, GAsyncResult* result, gpointer data) {
                    g_autofree char* current = static_cast<char*>(data);
                    g_auto(GStrv) identifiers = webkit_user_content_filter_store_fetch_identifiers_finish(WEBKIT_USER_CONTENT_FILTER_STORE(store), result);
                    for (char** identifier = identifiers; identifier && *identifier; ++identifier)
                        if (g_str_has_prefix(*identifier, identifierPrefix) && g_strcmp0(*identifier, current))
                            webkit_user_content_filter_store_remove(WEBKIT_USER_CONTENT_FILTER_STORE(store), *identifier, nullptr,
                                [](GObject* store, GAsyncResult* result, gpointer) {
                                    webkit_user_content_filter_store_remove_finish(WEBKIT_USER_CONTENT_FILTER_STORE(store), result, nullptr);
                                },
                                nullptr);
                },
                g_strdup(compilation->identifier.toUtf8().constData()));
        },
        new Compilation { this, m_identifier, {} });
}

void ContentFilter::apply(WebKitUserContentFilter* filter)
{
    if (m_filter)
        webkit_user_content_filter_unref(m_filter);
    m_filter = filter ? webkit_user_content_filter_ref(filter) : nullptr;
    for (WebKitUserContentManager* manager : std::as_const(m_managers)) {
        webkit_user_content_manager_remove_all_filters(manager);
        if (m_filter)
            webkit_user_content_manager_add_filter(manager, m_filter);
    }
}

void ContentFilter::addManager(WebKitUserContentManager* manager)
{
    m_managers.append(manager);
    if (m_filter)
        webkit_user_content_manager_add_filter(manager, m_filter);
}

void ContentFilter::removeManager(WebKitUserContentManager* manager)
{
    m_managers.removeOne(manager);
}

} // namespace QtWpeWebKit
