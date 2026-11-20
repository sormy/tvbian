// QWebChannel's messages to and from a page's script world, as QtWebEngine's qt.webChannelTransport
#pragma once

#include <QWebChannelAbstractTransport>

typedef struct _JSCValue JSCValue;
typedef struct _WebKitUserContentManager WebKitUserContentManager;
typedef struct _WebKitUserScript WebKitUserScript;
typedef struct _WebKitWebView WebKitWebView;

namespace QtWpeWebKit {

class WebChannelTransport : public QWebChannelAbstractTransport {
    Q_OBJECT
public:
    WebChannelTransport(WebKitWebView* webView, WebKitUserContentManager* manager, quint32 worldId);
    ~WebChannelTransport() override;

    void sendMessage(const QJsonObject& message) override;

private:
    static void receive(WebKitUserContentManager*, JSCValue* message, WebChannelTransport* self);

    WebKitWebView* m_webView;
    WebKitUserContentManager* m_manager;
    QByteArray m_world;
    WebKitUserScript* m_script;
};

} // namespace QtWpeWebKit
