// A page's session history, read from WebKitBackForwardList
#pragma once

#include <QDateTime>
#include <QList>
#include <QUrl>
#include <memory>

class QDataStream;
class QWebEnginePage;
typedef struct _WebKitBackForwardListItem WebKitBackForwardListItem;

class QWebEngineHistoryItem {
public:
    QWebEngineHistoryItem() = default;
    explicit QWebEngineHistoryItem(WebKitBackForwardListItem* item);

    QUrl originalUrl() const;
    QUrl url() const;
    QString title() const;
    QDateTime lastVisited() const { return {}; }
    QUrl iconUrl() const { return {}; }
    bool isValid() const { return bool(m_item); }

private:
    friend class QWebEngineHistory;
    std::shared_ptr<WebKitBackForwardListItem> m_item;
};

class QWebEngineHistory {
public:
    explicit QWebEngineHistory(QWebEnginePage* page)
        : m_page(page)
    {
    }
    QWebEngineHistory(const QWebEngineHistory&) = delete;
    QWebEngineHistory& operator=(const QWebEngineHistory&) = delete;

    // WebKit's history cannot be cleared from the UI process
    void clear() { }
    QList<QWebEngineHistoryItem> items() const;
    QList<QWebEngineHistoryItem> backItems(int maxItems) const;
    QList<QWebEngineHistoryItem> forwardItems(int maxItems) const;
    bool canGoBack() const;
    bool canGoForward() const;
    void back();
    void forward();
    void goToItem(const QWebEngineHistoryItem& item);
    QWebEngineHistoryItem backItem() const { return itemAt(currentItemIndex() - 1); }
    QWebEngineHistoryItem currentItem() const { return itemAt(currentItemIndex()); }
    QWebEngineHistoryItem forwardItem() const { return itemAt(currentItemIndex() + 1); }
    QWebEngineHistoryItem itemAt(int i) const;
    int currentItemIndex() const;
    int count() const;

private:
    friend QDataStream& operator<<(QDataStream& stream, const QWebEngineHistory& history);
    friend QDataStream& operator>>(QDataStream& stream, QWebEngineHistory& history);
    QWebEnginePage* m_page;
};

// WebKit's own session state, serialized
QDataStream& operator<<(QDataStream& stream, const QWebEngineHistory& history);
QDataStream& operator>>(QDataStream& stream, QWebEngineHistory& history);
