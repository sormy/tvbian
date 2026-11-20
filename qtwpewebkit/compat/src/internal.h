// What the compatibility classes share but QtWebEngine's API has no place for
#pragma once

#include <QByteArray>

class QWebEnginePage;
typedef struct _WebKitUserScript WebKitUserScript;
typedef struct _WebKitWebView WebKitWebView;

namespace QtWpeWebKit {

// Where QtWpeWebKit's own scripts run, out of the page's and the application's reach
inline constexpr char internalWorld[] = "QtWpeWebKit";

// QtWebEngine numbers its script worlds, WebKit names them; null for the page's own world
inline QByteArray worldName(quint32 worldId)
{
    return worldId ? "QtWpeWebKitWorld" + QByteArray::number(worldId) : QByteArray();
}

QWebEnginePage* pageOf(WebKitWebView* webView);

// Marks a WebKitDownload the user asked to save somewhere: a "Save as" download
inline constexpr char saveAsKey[] = "qtwpewebkit-save-as";

// Served from the application's Qt resources
inline constexpr char resourceScheme[] = "qrc";

WebKitUserScript* newUserScript(const QByteArray& source, quint32 worldId, bool allFrames, bool atDocumentStart);

} // namespace QtWpeWebKit
