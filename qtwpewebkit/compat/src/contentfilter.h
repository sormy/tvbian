// A profile's Adblock Plus filters, compiled once into a WebKit content blocker and applied to its pages
#pragma once

#include <QList>
#include <QObject>

typedef struct _WebKitUserContentFilter WebKitUserContentFilter;
typedef struct _WebKitUserContentFilterStore WebKitUserContentFilterStore;
typedef struct _WebKitUserContentManager WebKitUserContentManager;

namespace QtWpeWebKit {

class ContentFilter : public QObject {
public:
    explicit ContentFilter(QObject* parent);
    ~ContentFilter() override;

    // Compiles in the background, unless compiled before
    void setAdblockFilters(const QString& filterLists);
    void addManager(WebKitUserContentManager* manager);
    void removeManager(WebKitUserContentManager* manager);

private:
    void compile(const QString& filterLists);
    void save(const QByteArray& rules);
    void apply(WebKitUserContentFilter* filter);

    WebKitUserContentFilterStore* m_store;
    WebKitUserContentFilter* m_filter = nullptr;
    // Of the filters asked for last, so a late compilation of older ones is dropped
    QString m_identifier;
    QList<WebKitUserContentManager*> m_managers;
};

} // namespace QtWpeWebKit
