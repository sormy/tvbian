#include "webchanneltransport.h"

#include "internal.h"

#include <QJsonDocument>
#include <QJsonObject>
#include <wpe/webkit.h>

namespace QtWpeWebKit {

static const char handlerName[] = "qtwebchannel";
static const char transportScript[] = R"(
window.qt = { webChannelTransport: {
    send(message) { window.webkit.messageHandlers.qtwebchannel.postMessage(message); },
    deliver(message) { if (this.onmessage) this.onmessage({ data: message }); },
} };)";

static const char* nameOrNull(const QByteArray& world)
{
    return world.isNull() ? nullptr : world.constData();
}

WebChannelTransport::WebChannelTransport(WebKitWebView* webView, WebKitUserContentManager* manager, quint32 worldId)
    : m_webView(webView)
    , m_manager(manager)
    , m_world(worldName(worldId))
    , m_script(newUserScript(transportScript, worldId, false, true))
{
    webkit_user_content_manager_add_script(m_manager, m_script);
    webkit_user_content_manager_register_script_message_handler(m_manager, handlerName, nameOrNull(m_world));
    g_signal_connect(m_manager, "script-message-received::qtwebchannel", G_CALLBACK(receive), this);
}

WebChannelTransport::~WebChannelTransport()
{
    g_signal_handlers_disconnect_by_data(m_manager, this);
    webkit_user_content_manager_unregister_script_message_handler(m_manager, handlerName, nameOrNull(m_world));
    webkit_user_content_manager_remove_script(m_manager, m_script);
    webkit_user_script_unref(m_script);
}

void WebChannelTransport::sendMessage(const QJsonObject& message)
{
    const QByteArray script = "qt.webChannelTransport.deliver(" + QJsonDocument(message).toJson(QJsonDocument::Compact) + ")";
    webkit_web_view_evaluate_javascript(m_webView, script.constData(), script.size(), nameOrNull(m_world), nullptr,
        nullptr, nullptr, nullptr);
}

void WebChannelTransport::receive(WebKitUserContentManager*, JSCValue* message, WebChannelTransport* self)
{
    g_autofree char* text = jsc_value_to_string(message);
    Q_EMIT self->messageReceived(QJsonDocument::fromJson(text).object(), self);
}

} // namespace QtWpeWebKit
