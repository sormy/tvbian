#include "qwebenginehistory.h"

#include "qwebenginepage.h"

#include <QDataStream>
#include <wpe/webkit.h>

QWebEngineHistoryItem::QWebEngineHistoryItem(WebKitBackForwardListItem* item)
{
    if (item)
        m_item.reset(WEBKIT_BACK_FORWARD_LIST_ITEM(g_object_ref(item)), g_object_unref);
}

QUrl QWebEngineHistoryItem::originalUrl() const
{
    return m_item ? QUrl::fromEncoded(webkit_back_forward_list_item_get_original_uri(m_item.get())) : QUrl();
}

QUrl QWebEngineHistoryItem::url() const
{
    return m_item ? QUrl::fromEncoded(webkit_back_forward_list_item_get_uri(m_item.get())) : QUrl();
}

QString QWebEngineHistoryItem::title() const
{
    return m_item ? QString::fromUtf8(webkit_back_forward_list_item_get_title(m_item.get())) : QString();
}

static WebKitBackForwardList* listOf(QWebEnginePage* page)
{
    return webkit_web_view_get_back_forward_list(page->webKitWebView());
}

QList<QWebEngineHistoryItem> QWebEngineHistory::items() const
{
    QList<QWebEngineHistoryItem> list;
    for (int i = 0; i < count(); ++i)
        list.append(itemAt(i));
    return list;
}

QList<QWebEngineHistoryItem> QWebEngineHistory::backItems(int maxItems) const
{
    return items().mid(qMax(0, currentItemIndex() - maxItems), qMin(maxItems, currentItemIndex()));
}

QList<QWebEngineHistoryItem> QWebEngineHistory::forwardItems(int maxItems) const
{
    return items().mid(currentItemIndex() + 1, maxItems);
}

bool QWebEngineHistory::canGoBack() const
{
    return webkit_web_view_can_go_back(m_page->webKitWebView());
}

bool QWebEngineHistory::canGoForward() const
{
    return webkit_web_view_can_go_forward(m_page->webKitWebView());
}

void QWebEngineHistory::back()
{
    webkit_web_view_go_back(m_page->webKitWebView());
}

void QWebEngineHistory::forward()
{
    webkit_web_view_go_forward(m_page->webKitWebView());
}

void QWebEngineHistory::goToItem(const QWebEngineHistoryItem& item)
{
    if (item.isValid())
        webkit_web_view_go_to_back_forward_list_item(m_page->webKitWebView(), item.m_item.get());
}

// WebKit counts from the current item, QtWebEngine from the oldest
QWebEngineHistoryItem QWebEngineHistory::itemAt(int i) const
{
    return QWebEngineHistoryItem(webkit_back_forward_list_get_nth_item(listOf(m_page), i - currentItemIndex()));
}

int QWebEngineHistory::currentItemIndex() const
{
    GList* back = webkit_back_forward_list_get_back_list(listOf(m_page));
    const int index = g_list_length(back);
    g_list_free(back);
    return index;
}

int QWebEngineHistory::count() const
{
    return webkit_back_forward_list_get_length(listOf(m_page));
}

QDataStream& operator<<(QDataStream& stream, const QWebEngineHistory& history)
{
    WebKitWebViewSessionState* state = webkit_web_view_get_session_state(history.m_page->webKitWebView());
    g_autoptr(GBytes) bytes = webkit_web_view_session_state_serialize(state);
    webkit_web_view_session_state_unref(state);
    gsize size = 0;
    const auto* data = static_cast<const char*>(g_bytes_get_data(bytes, &size));
    return stream << QByteArray(data, size);
}

// Like QtWebEngine, the page goes to the restored current item
QDataStream& operator>>(QDataStream& stream, QWebEngineHistory& history)
{
    QByteArray data;
    stream >> data;
    g_autoptr(GBytes) bytes = g_bytes_new(data.constData(), data.size());
    WebKitWebViewSessionState* state = webkit_web_view_session_state_new(bytes);
    if (!state)
        return stream;
    WebKitWebView* webView = history.m_page->webKitWebView();
    webkit_web_view_restore_session_state(webView, state);
    webkit_web_view_session_state_unref(state);
    if (auto* current = webkit_back_forward_list_get_current_item(webkit_web_view_get_back_forward_list(webView)))
        webkit_web_view_go_to_back_forward_list_item(webView, current);
    return stream;
}
