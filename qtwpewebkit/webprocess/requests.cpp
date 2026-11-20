// Loaded into each web process: every request of a page waits for the UI process's interceptors to answer, and
// each console message of a page goes to its view
#include "requestprotocol.h"

#include <gio/gunixsocketaddress.h>
#include <wpe/webkit-web-process-extension.h>

static GSocketConnection* connection;

static bool readAll(GInputStream* input, void* buffer, gsize size)
{
    gsize bytesRead = 0;
    return g_input_stream_read_all(input, buffer, size, &bytesRead, nullptr, nullptr) && bytesRead == size;
}

static GVariant* exchange(GVariant* message)
{
    g_autoptr(GVariant) request = g_variant_ref_sink(message);
    GOutputStream* output = g_io_stream_get_output_stream(G_IO_STREAM(connection));
    GInputStream* input = g_io_stream_get_input_stream(G_IO_STREAM(connection));
    guint32 size = g_variant_get_size(request);
    if (g_output_stream_write_all(output, &size, sizeof size, nullptr, nullptr, nullptr)
        && g_output_stream_write_all(output, g_variant_get_data(request), size, nullptr, nullptr, nullptr)
        && readAll(input, &size, sizeof size)) {
        gpointer data = g_malloc(size);
        g_autoptr(GBytes) reply = g_bytes_new_take(data, size);
        if (readAll(input, data, size))
            return g_variant_ref_sink(g_variant_new_from_bytes(G_VARIANT_TYPE(QtWpeWebKit::replyFormat), reply, FALSE));
    }
    // The UI process is gone: requests go out as they are
    g_clear_object(&connection);
    return nullptr;
}

static const char* headerOf(SoupMessageHeaders* headers, const char* name)
{
    const char* value = headers ? soup_message_headers_get_one(headers, name) : nullptr;
    return value ? value : "";
}

static gboolean sendRequest(WebKitWebPage* page, WebKitURIRequest* request, WebKitURIResponse*, gpointer)
{
    const char* url = webkit_uri_request_get_uri(request);
    if (!connection || g_str_has_prefix(url, "data:"))
        return FALSE;
    SoupMessageHeaders* headers = webkit_uri_request_get_http_headers(request);
    const char* pageUrl = webkit_web_page_get_uri(page);
    const char* method = webkit_uri_request_get_http_method(request);
    g_autoptr(GVariant) reply = exchange(g_variant_new(QtWpeWebKit::requestFormat, webkit_web_page_get_id(page), url,
        pageUrl ? pageUrl : "", method ? method : "GET", headerOf(headers, "Sec-Fetch-Dest"), headerOf(headers, "Accept")));
    if (!reply)
        return FALSE;
    gboolean blocked;
    const char* redirectUrl;
    g_autoptr(GVariantIter) newHeaders = nullptr;
    g_variant_get(reply, "(b&sa{ss})", &blocked, &redirectUrl, &newHeaders);
    if (*redirectUrl)
        webkit_uri_request_set_uri(request, redirectUrl);
    const char *name, *value;
    while (headers && g_variant_iter_loop(newHeaders, "{&s&s}", &name, &value))
        soup_message_headers_replace(headers, name, value);
    return blocked;
}

static void sendConsoleMessage(WebKitWebPage* page, WebKitConsoleMessage* message, gpointer)
{
    const char* source = webkit_console_message_get_source_id(message);
    const auto level = webkit_console_message_get_level(message);
    webkit_web_page_send_message_to_view(page,
        webkit_user_message_new(QtWpeWebKit::consoleMessageName,
            g_variant_new(QtWpeWebKit::consoleMessageFormat,
                level == WEBKIT_CONSOLE_MESSAGE_LEVEL_ERROR         ? QtWpeWebKit::ConsoleError
                    : level == WEBKIT_CONSOLE_MESSAGE_LEVEL_WARNING ? QtWpeWebKit::ConsoleWarning
                                                                    : QtWpeWebKit::ConsoleInfo,
                webkit_console_message_get_text(message), source ? source : "", webkit_console_message_get_line(message))),
        nullptr, nullptr, nullptr);
}

extern "C" G_MODULE_EXPORT void webkit_web_process_extension_initialize_with_user_data(
    WebKitWebProcessExtension* extension, const GVariant* serverPath)
{
    g_autoptr(GSocketAddress) address = g_unix_socket_address_new(g_variant_get_string(const_cast<GVariant*>(serverPath), nullptr));
    g_autoptr(GSocketClient) client = g_socket_client_new();
    connection = g_socket_client_connect(client, G_SOCKET_CONNECTABLE(address), nullptr, nullptr);
    g_signal_connect(extension, "page-created", G_CALLBACK(+[](WebKitWebProcessExtension*, WebKitWebPage* page) {
        g_signal_connect(page, "send-request", G_CALLBACK(sendRequest), nullptr);
        g_signal_connect(page, "console-message-sent", G_CALLBACK(sendConsoleMessage), nullptr);
    }), nullptr);
}
