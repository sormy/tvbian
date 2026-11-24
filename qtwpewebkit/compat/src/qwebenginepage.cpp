#include "qwebenginepage.h"

#include "contentfilter.h"
#include "internal.h"
#include "platform.h"
#include "qwebenginehistory.h"
#include "qwebengineprofile.h"
#include "qwebenginescriptcollection.h"
#include "qwebenginesettings.h"
#include "qwebengineview.h"
#include "requestprotocol.h"
#include "requestinterception.h"
#include "webchanneltransport.h"

#include <QAction>
#include <QJsonArray>
#include <QJsonDocument>
#include <QLoggingCategory>
#include <QWebChannel>
#include <climits>
#include <cmath>
#include <wpe/webkit.h>

static const char pageKey[] = "qtwpewebkit-page";
static const char stateHandler[] = "qtwpewebkitState";
// What QtWebEngine knows of a page without asking it: scroll position, contents size, selection, focus in an editable field
static const char stateScript[] = R"(
(function() {
    const post = state => window.webkit.messageHandlers.qtwpewebkitState.postMessage(state);
    function reportGeometry() {
        const root = document.documentElement;
        post({ scroll: [scrollX, scrollY], contents: [root.scrollWidth, root.scrollHeight] });
    }
    function reportSelection() {
        const field = document.activeElement;
        const inField = field && typeof field.selectionStart === 'number';
        post({
            selection: inField ? field.value.substring(field.selectionStart, field.selectionEnd) : getSelection().toString(),
            editing: Boolean(inField || (field && field.isContentEditable)),
        });
    }
    addEventListener('scroll', reportGeometry, { passive: true });
    for (const event of ['selectionchange', 'select', 'focusin', 'focusout'])
        document.addEventListener(event, reportSelection, true);
    addEventListener('DOMContentLoaded', () => {
        const observer = new ResizeObserver(reportGeometry);
        observer.observe(document.documentElement);
        if (document.body)
            observer.observe(document.body);
    });
})();)";
static const guint middleButton = 2;

// where QtWebEngine logs a page's console messages by default
Q_LOGGING_CATEGORY(jsConsole, "js")
// While a page handles a window.open: the first page made then is related to its view, so the popup keeps
// window.opener; WebKit gives the window's features to that one view only
static WebKitWebView* openerOfNewPages = nullptr;
static QWebEnginePage* relatedPageOfNewWindow = nullptr;

static WebKitWebView* newWebView(WebKitWebView* related, WebKitNetworkSession* session, WebKitUserContentManager* contents,
    WebKitSettings* settings)
{
    // a related view takes its display and network session from the view it is related to
    if (related)
        return WEBKIT_WEB_VIEW(g_object_new(WEBKIT_TYPE_WEB_VIEW, "related-view", related, "user-content-manager", contents,
            "settings", settings, nullptr));
    return WEBKIT_WEB_VIEW(g_object_new(WEBKIT_TYPE_WEB_VIEW, "display", QtWpeWebKit::display(), "network-session", session,
        "user-content-manager", contents, "settings", settings, nullptr));
}

QWebEnginePage* QtWpeWebKit::pageOf(WebKitWebView* webView)
{
    return static_cast<QWebEnginePage*>(g_object_get_data(G_OBJECT(webView), pageKey));
}

static QStringList stringsOf(const gchar* const* strings)
{
    QStringList list;
    for (; strings && *strings; ++strings)
        list.append(QString::fromUtf8(*strings));
    return list;
}

static QUrl urlOf(WebKitNavigationAction* action)
{
    return QUrl::fromEncoded(webkit_uri_request_get_uri(webkit_navigation_action_get_request(action)));
}

// WebKit's "other" covers the application's loads and the page's scripts; QtWebEngine counts a script's as a link's
static QWebEnginePage::NavigationType navigationTypeOf(WebKitNavigationAction* action, bool requestedByApplication)
{
    if (webkit_navigation_action_is_redirect(action))
        return QWebEnginePage::NavigationTypeRedirect;
    switch (webkit_navigation_action_get_navigation_type(action)) {
    case WEBKIT_NAVIGATION_TYPE_LINK_CLICKED:
        return QWebEnginePage::NavigationTypeLinkClicked;
    case WEBKIT_NAVIGATION_TYPE_FORM_SUBMITTED:
    case WEBKIT_NAVIGATION_TYPE_FORM_RESUBMITTED:
        return QWebEnginePage::NavigationTypeFormSubmitted;
    case WEBKIT_NAVIGATION_TYPE_BACK_FORWARD:
        return QWebEnginePage::NavigationTypeBackForward;
    case WEBKIT_NAVIGATION_TYPE_RELOAD:
        return QWebEnginePage::NavigationTypeReload;
    default:
        return requestedByApplication ? QWebEnginePage::NavigationTypeTyped : QWebEnginePage::NavigationTypeLinkClicked;
    }
}

static QVariant numberOf(double number)
{
    const bool integral = number == std::trunc(number) && number >= INT_MIN && number <= INT_MAX;
    return integral ? QVariant(int(number)) : QVariant(number);
}

// As QtWebEngine converts: null and undefined are invalid, a Date is its seconds since the epoch
static QVariant variantOf(JSCValue* value)
{
    if (!value || jsc_value_is_null(value) || jsc_value_is_undefined(value))
        return {};
    if (jsc_value_is_boolean(value))
        return bool(jsc_value_to_boolean(value));
    if (jsc_value_is_number(value))
        return numberOf(jsc_value_to_double(value));
    if (jsc_value_is_string(value)) {
        g_autofree char* string = jsc_value_to_string(value);
        return QString::fromUtf8(string);
    }
    if (jsc_value_object_is_instance_of(value, "Date")) {
        g_autoptr(JSCValue) milliseconds = jsc_value_object_invoke_method(value, "getTime", G_TYPE_NONE);
        return jsc_value_to_double(milliseconds) / 1000;
    }
    if (jsc_value_is_array(value)) {
        g_autoptr(JSCValue) length = jsc_value_object_get_property(value, "length");
        QVariantList list;
        for (guint index = 0, count = jsc_value_to_int32(length); index < count; ++index) {
            g_autoptr(JSCValue) item = jsc_value_object_get_property_at_index(value, index);
            list.append(variantOf(item));
        }
        return list;
    }
    QVariantMap map;
    g_auto(GStrv) names = jsc_value_object_enumerate_properties(value);
    for (char** name = names; name && *name; ++name) {
        g_autoptr(JSCValue) property = jsc_value_object_get_property(value, *name);
        map.insert(QString::fromUtf8(*name), variantOf(property));
    }
    return map;
}

// The title QtWebEngine shows for a page without one: its URL, the way Chromium formats it
static QString untitledPageTitle(const QUrl& url)
{
    if (url.isEmpty())
        return {};
    if (url.isLocalFile())
        return url.fileName();
    const bool bareHost = url.path() == QLatin1String("/") && !url.hasQuery() && !url.hasFragment();
    const QUrl::FormattingOptions options = QUrl::RemoveUserInfo | (bareHost ? QUrl::StripTrailingSlash : QUrl::None);
    if (url.scheme() == QLatin1String("http"))
        return url.toString(options | QUrl::RemoveScheme).mid(qstrlen("//"));
    return url.toString(options);
}

using ScriptCallback = std::function<void(JSCValue*)>;

// The callback is dropped with the page
static void evaluate(QWebEnginePage* page, const QByteArray& script, const QByteArray& world, const ScriptCallback& callback)
{
    struct Call {
        QPointer<QWebEnginePage> page;
        ScriptCallback callback;
    };
    webkit_web_view_evaluate_javascript(page->webKitWebView(), script.constData(), script.size(),
        world.isNull() ? nullptr : world.constData(), nullptr, nullptr,
        [](GObject* view, GAsyncResult* result, gpointer data) {
            std::unique_ptr<Call> call(static_cast<Call*>(data));
            g_autoptr(JSCValue) value = webkit_web_view_evaluate_javascript_finish(WEBKIT_WEB_VIEW(view), result, nullptr);
            if (call->page && call->callback)
                call->callback(value);
        },
        new Call { page, callback });
}

// WebKit drops a script world, and the globals scripts set in it, when nothing refers to it any more
static void keepWorld(const QByteArray& world)
{
    static QHash<QByteArray, WebKitUserScript*> worlds;
    if (!world.isNull() && !worlds.contains(world))
        worlds.insert(world, webkit_user_script_new_for_world("", WEBKIT_USER_CONTENT_INJECT_TOP_FRAME,
            WEBKIT_USER_SCRIPT_INJECT_AT_DOCUMENT_END, world.constData(), nullptr, nullptr));
}

static WPEToplevel* toplevelOf(WebKitWebView* webView)
{
    return wpe_view_get_toplevel(webkit_web_view_get_wpe_view(webView));
}

static bool isFullScreen(WebKitWebView* webView)
{
    return wpe_toplevel_get_state(toplevelOf(webView)) & WPE_TOPLEVEL_STATE_FULLSCREEN;
}

// Set on a view while it leaves the fullscreen its application refused
static const char fullScreenRefusedKey[] = "qtwpewebkit-fullscreen-refused";

// WebKit's page follows its toplevel's state into and out of fullscreen
static void setFullScreen(WebKitWebView* webView, bool on)
{
    const guint state = wpe_toplevel_get_state(toplevelOf(webView));
    wpe_toplevel_state_changed(toplevelOf(webView),
        static_cast<WPEToplevelState>(on ? state | WPE_TOPLEVEL_STATE_FULLSCREEN : state & ~WPE_TOPLEVEL_STATE_FULLSCREEN));
}

struct QWebEnginePage::WebViewSignals {
    static gboolean decidePolicy(WebKitWebView*, WebKitPolicyDecision* decision, WebKitPolicyDecisionType type, QWebEnginePage* page)
    {
        if (type == WEBKIT_POLICY_DECISION_TYPE_RESPONSE) {
            noteHttpError(WEBKIT_RESPONSE_POLICY_DECISION(decision), page);
            return FALSE;
        }
        if (type != WEBKIT_POLICY_DECISION_TYPE_NAVIGATION_ACTION)
            return FALSE;
        auto* action = webkit_navigation_policy_decision_get_navigation_action(WEBKIT_NAVIGATION_POLICY_DECISION(decision));
        // A frame's navigation is asked about alone: the page's own load state is the main frame's
        WebKitFrameInfo* target = webkit_navigation_action_get_target_frame_info(action);
        if (target && !webkit_frame_info_is_main_frame(target)) {
            if (page->acceptNavigationRequest(urlOf(action), navigationTypeOf(action, false), false))
                webkit_policy_decision_use(decision);
            else
                webkit_policy_decision_ignore(decision);
            return TRUE;
        }
        const bool requestedByApplication = std::exchange(page->m_loadRequested, false);
        page->m_navigationType = page->m_redirecting ? NavigationTypeRedirect : navigationTypeOf(action, requestedByApplication);
        if (page->acceptNavigationRequest(urlOf(action), page->m_navigationType, true)) {
            webkit_policy_decision_use(decision);
            return TRUE;
        }
        webkit_policy_decision_ignore(decision);
        // A refused redirect fails the load it continues
        if (std::exchange(page->m_redirecting, false)) {
            page->m_loadFailed = true;
            if (!page->isLoading())
                page->finishLoad();
        }
        return TRUE;
    }

    // QtWebEngine counts a page the server answers with an HTTP error as a failed load
    static void noteHttpError(WebKitResponsePolicyDecision* decision, QWebEnginePage* page)
    {
        const guint firstHttpError = 400;
        if (webkit_response_policy_decision_is_main_frame_main_resource(decision)
            && webkit_uri_response_get_status_code(webkit_response_policy_decision_get_response(decision)) >= firstHttpError)
            page->m_loadFailed = true;
    }

    // Where a popup or a click with these buttons and keys opens a link, as in Chromium
    static QWebEngineNewWindowRequest::DestinationType destinationOf(WebKitNavigationAction* action)
    {
        if (webkit_navigation_action_is_popup(action))
            return QWebEngineNewWindowRequest::InNewDialog;
        const guint modifiers = webkit_navigation_action_get_modifiers(action);
        const bool shift = modifiers & WPE_MODIFIER_KEYBOARD_SHIFT;
        if (webkit_navigation_action_get_mouse_button(action) == middleButton || (modifiers & WPE_MODIFIER_KEYBOARD_CONTROL))
            return shift ? QWebEngineNewWindowRequest::InNewTab : QWebEngineNewWindowRequest::InNewBackgroundTab;
        return shift ? QWebEngineNewWindowRequest::InNewWindow : QWebEngineNewWindowRequest::InNewTab;
    }

    // A page made for the request is handed to WebKit, which loads it with window.opener kept; any other loads
    // the URL itself, and WebKit gets no view back
    static WebKitWebView* create(WebKitWebView* view, WebKitNavigationAction* action, QWebEnginePage* page)
    {
        const QUrl url = urlOf(action);
        QWebEngineNewWindowRequest request(destinationOf(action), url, webkit_navigation_action_is_user_gesture(action), view);
        openerOfNewPages = view;
        relatedPageOfNewWindow = nullptr;
        Q_EMIT page->newWindowRequested(request);
        openerOfNewPages = nullptr;
        QWebEnginePage* opened = request.openedPage();
        if (!opened)
            return nullptr;
        if (opened == std::exchange(relatedPageOfNewWindow, nullptr))
            return WEBKIT_WEB_VIEW(g_object_ref(opened->m_webView));
        // Another page took the window: WebKit would not find the window's features on it. It loads the address
        // itself, the popup without an opener
        webkit_web_view_load_uri(opened->m_webView, url.toEncoded().constData());
        return nullptr;
    }

    static gboolean scriptDialog(WebKitWebView*, WebKitScriptDialog* dialog, QWebEnginePage* page)
    {
        const QUrl origin = page->url();
        const QString message = QString::fromUtf8(webkit_script_dialog_get_message(dialog));
        switch (webkit_script_dialog_get_dialog_type(dialog)) {
        case WEBKIT_SCRIPT_DIALOG_ALERT:
            page->javaScriptAlert(origin, message);
            break;
        case WEBKIT_SCRIPT_DIALOG_CONFIRM:
        case WEBKIT_SCRIPT_DIALOG_BEFORE_UNLOAD_CONFIRM:
            webkit_script_dialog_confirm_set_confirmed(dialog, page->javaScriptConfirm(origin, message));
            break;
        case WEBKIT_SCRIPT_DIALOG_PROMPT: {
            QString text;
            const QString defaultText = QString::fromUtf8(webkit_script_dialog_prompt_get_default_text(dialog));
            if (page->javaScriptPrompt(origin, message, defaultText, &text))
                webkit_script_dialog_prompt_set_text(dialog, text.toUtf8().constData());
            break;
        }
        }
        return TRUE;
    }

    static gboolean runFileChooser(WebKitWebView*, WebKitFileChooserRequest* request, QWebEnginePage* page)
    {
        const QStringList files = page->chooseFiles(
            webkit_file_chooser_request_get_select_multiple(request) ? FileSelectOpenMultiple : FileSelectOpen,
            stringsOf(webkit_file_chooser_request_get_selected_files(request)),
            stringsOf(webkit_file_chooser_request_get_mime_types(request)));
        if (files.isEmpty()) {
            webkit_file_chooser_request_cancel(request);
            return TRUE;
        }
        QList<QByteArray> paths;
        std::vector<const gchar*> pathPointers;
        for (const QString& file : files)
            pathPointers.push_back(paths.emplace_back(file.toUtf8()).constData());
        pathPointers.push_back(nullptr);
        webkit_file_chooser_request_select_files(request, pathPointers.data());
        return TRUE;
    }

    static void loadChanged(WebKitWebView*, WebKitLoadEvent event, QWebEnginePage* page)
    {
        // WebKit's error page is a load of its own; QtWebEngine's is part of the failed one
        if (event == WEBKIT_LOAD_STARTED)
            page->m_loadingErrorPage = std::exchange(page->m_errorPageNext, false);
        if (page->m_loadingErrorPage) {
            page->m_loadingErrorPage = event != WEBKIT_LOAD_FINISHED;
            return;
        }
        // The redirected load ends and the new one starts as one load
        if (page->m_redirecting) {
            if (event == WEBKIT_LOAD_STARTED) {
                page->m_redirecting = false;
                page->m_loadFailed = false;
            }
            return;
        }
        if (event == WEBKIT_LOAD_STARTED) {
            page->emitLoadFinished();
            ++page->m_loadCount;
            page->m_loadFailed = false;
            page->m_editing = false;
            Q_EMIT page->loadStarted();
        } else if (event == WEBKIT_LOAD_FINISHED)
            page->finishLoad();
    }

    // WebKit reports the failure, then the load's end
    static gboolean loadFailed(WebKitWebView*, WebKitLoadEvent, char*, GError* error, QWebEnginePage* page)
    {
        page->m_loadFailed = true;
        if (!page->settings()->testAttribute(QWebEngineSettings::ErrorPageEnabled))
            return TRUE;
        page->m_errorPageNext = QtWpeWebKit::showsErrorPage(error);
        return FALSE;
    }

    // A refused page enters fullscreen and leaves it at once: WebKit has no other way back. That leaving is no
    // request of the page's, so the application hears nothing more, as from QtWebEngine
    static gboolean enterFullScreen(WebKitWebView*, QWebEnginePage* page)
    {
        Q_EMIT page->fullScreenRequested(QWebEngineFullScreenRequest(page->url(), true, [page = QPointer(page)](bool on) {
            if (!page)
                return;
            WebKitWebView* webView = page->webKitWebView();
            setFullScreen(webView, true);
            if (on)
                return;
            g_object_set_data(G_OBJECT(webView), fullScreenRefusedKey, GINT_TO_POINTER(TRUE));
            setFullScreen(webView, false);
        }));
        return TRUE;
    }

    // The page has left already, whatever Qt answers; WebKit finishes leaving itself when the toplevel was not fullscreen
    static gboolean leaveFullScreen(WebKitWebView* webView, QWebEnginePage* page)
    {
        const bool wasFullScreen = isFullScreen(webView);
        const bool refused = g_object_steal_data(G_OBJECT(webView), fullScreenRefusedKey);
        setFullScreen(webView, false);
        if (!refused)
            Q_EMIT page->fullScreenRequested(QWebEngineFullScreenRequest(page->url(), false, [](bool) { }));
        return wasFullScreen;
    }

    static void stateReceived(WebKitUserContentManager*, JSCValue* message, QWebEnginePage* page)
    {
        const QVariantMap state = variantOf(message).toMap();
        if (state.contains(QStringLiteral("scroll"))) {
            const QVariantList scroll = state.value(QStringLiteral("scroll")).toList();
            const QVariantList contents = state.value(QStringLiteral("contents")).toList();
            const QPointF position(scroll.value(0).toReal(), scroll.value(1).toReal());
            const QSizeF size(contents.value(0).toReal(), contents.value(1).toReal());
            if (position != page->m_scrollPosition)
                Q_EMIT page->scrollPositionChanged(page->m_scrollPosition = position);
            if (size != page->m_contentsSize)
                Q_EMIT page->contentsSizeChanged(page->m_contentsSize = size);
        } else {
            page->m_editing = state.value(QStringLiteral("editing")).toBool();
            const QString text = state.value(QStringLiteral("selection")).toString();
            if (text != page->m_selectedText) {
                page->m_selectedText = text;
                Q_EMIT page->selectionChanged();
            }
        }
    }

    // WebKit has no menu of its own to show
    static gboolean contextMenu(WebKitWebView*, WebKitContextMenu* menu, WebKitHitTestResult* hit, QWebEnginePage* page)
    {
        if (page->m_view)
            page->m_view->requestContextMenu(menu, hit);
        return TRUE;
    }

    static void mouseTargetChanged(WebKitWebView*, WebKitHitTestResult* hit, guint, QWebEnginePage* page)
    {
        const char* link = webkit_hit_test_result_context_is_link(hit) ? webkit_hit_test_result_get_link_uri(hit) : "";
        Q_EMIT page->linkHovered(QString::fromUtf8(link));
    }

    static void finishFind(QWebEnginePage* page, int matchCount)
    {
        int& active = page->m_findActiveMatch;
        switch (page->m_findMove) {
        case FindMove::First:
            active = 1;
            break;
        case FindMove::Last:
            active = matchCount;
            break;
        case FindMove::Next:
            active = active % qMax(matchCount, 1) + 1;
            break;
        case FindMove::Previous:
            active = active > 1 ? active - 1 : matchCount;
            break;
        }
        if (!matchCount)
            active = 0;
        const QWebEngineFindTextResult result(matchCount, active);
        if (page->m_findCallback)
            page->m_findCallback(result);
        Q_EMIT page->findTextFinished(result);
    }

    static gboolean userMessageReceived(WebKitWebView*, WebKitUserMessage* message, QWebEnginePage* page)
    {
        if (g_strcmp0(webkit_user_message_get_name(message), QtWpeWebKit::consoleMessageName))
            return FALSE;
        guint level, line;
        const char *text, *source;
        g_variant_get(webkit_user_message_get_parameters(message), QtWpeWebKit::consoleMessageFormat, &level, &text, &source, &line);
        page->javaScriptConsoleMessage(QWebEnginePage::JavaScriptConsoleMessageLevel(level), QString::fromUtf8(text),
            int(line), QString::fromUtf8(source));
        return TRUE;
    }

    static void connect(QWebEnginePage* page)
    {
        WebKitWebView* view = page->m_webView;
        g_signal_connect(view, "decide-policy", G_CALLBACK(decidePolicy), page);
        g_signal_connect(view, "create", G_CALLBACK(create), page);
        g_signal_connect(view, "script-dialog", G_CALLBACK(scriptDialog), page);
        g_signal_connect(view, "run-file-chooser", G_CALLBACK(runFileChooser), page);
        g_signal_connect(view, "load-changed", G_CALLBACK(loadChanged), page);
        g_signal_connect(view, "load-failed", G_CALLBACK(loadFailed), page);
        g_signal_connect(view, "mouse-target-changed", G_CALLBACK(mouseTargetChanged), page);
        g_signal_connect(view, "context-menu", G_CALLBACK(contextMenu), page);
        g_signal_connect(view, "enter-fullscreen", G_CALLBACK(enterFullScreen), page);
        g_signal_connect(view, "leave-fullscreen", G_CALLBACK(leaveFullScreen), page);
        g_signal_connect(view, "user-message-received", G_CALLBACK(userMessageReceived), page);
        g_signal_connect_swapped(view, "close", G_CALLBACK(+[](QWebEnginePage* page) {
            Q_EMIT page->windowCloseRequested();
        }), page);
        g_signal_connect_swapped(view, "web-process-terminated", G_CALLBACK(+[](QWebEnginePage* page) {
            Q_EMIT page->renderProcessTerminated(CrashedTerminationStatus, 0);
        }), page);
        g_signal_connect_swapped(view, "notify::title", G_CALLBACK(+[](QWebEnginePage* page) {
            page->updateTitle(webkit_web_view_get_title(page->m_webView));
        }), page);
        g_signal_connect_swapped(view, "notify::uri", G_CALLBACK(+[](QWebEnginePage* page) {
            Q_EMIT page->urlChanged(page->url());
        }), page);
        g_signal_connect_swapped(view, "notify::estimated-load-progress", G_CALLBACK(+[](QWebEnginePage* page) {
            Q_EMIT page->loadProgress(qRound(100 * webkit_web_view_get_estimated_load_progress(page->m_webView)));
        }), page);
        g_signal_connect_swapped(view, "notify::page-icons", G_CALLBACK(+[](QWebEnginePage* page) {
            Q_EMIT page->iconChanged(page->icon());
        }), page);
        g_signal_connect_swapped(view, "notify::is-muted", G_CALLBACK(+[](QWebEnginePage* page) {
            Q_EMIT page->audioMutedChanged(page->isAudioMuted());
        }), page);
        g_signal_connect_swapped(view, "notify::is-playing-audio", G_CALLBACK(+[](QWebEnginePage* page) {
            Q_EMIT page->recentlyAudibleChanged(page->recentlyAudible());
        }), page);

        g_signal_connect(page->m_userContentManager, "script-message-received::qtwpewebkitState", G_CALLBACK(stateReceived), page);

        auto* finder = webkit_web_view_get_find_controller(view);
        g_signal_connect_swapped(finder, "found-text", G_CALLBACK(+[](QWebEnginePage* page, guint matchCount) {
            finishFind(page, matchCount);
        }), page);
        g_signal_connect_swapped(finder, "failed-to-find-text", G_CALLBACK(+[](QWebEnginePage* page) {
            finishFind(page, 0);
        }), page);
    }
};

QWebEnginePage::QWebEnginePage(QObject* parent)
    : QWebEnginePage(QWebEngineProfile::defaultProfile(), parent)
{
}

QWebEnginePage::QWebEnginePage(QWebEngineProfile* profile, QObject* parent)
    : QObject(parent)
    , m_profile(profile)
    , m_settings(std::make_unique<QWebEngineSettings>(profile->settings()))
    , m_userContentManager(webkit_user_content_manager_new())
    // A related view shares its opener's network session: only one of the same profile
    , m_openerView(openerOfNewPages && webkit_web_view_get_network_session(openerOfNewPages) == profile->networkSession()
              ? openerOfNewPages
              : nullptr)
    , m_webView(newWebView(m_openerView, profile->networkSession(), m_userContentManager, m_settings->webKitSettings()))
    , m_history(std::make_unique<QWebEngineHistory>(this))
    , m_stateScript(webkit_user_script_new_for_world(stateScript, WEBKIT_USER_CONTENT_INJECT_TOP_FRAME,
          WEBKIT_USER_SCRIPT_INJECT_AT_DOCUMENT_START, QtWpeWebKit::internalWorld, nullptr, nullptr))
{
    if (m_openerView) {
        relatedPageOfNewWindow = this;
        openerOfNewPages = nullptr;
    }
    webkit_user_content_manager_add_script(m_userContentManager, m_stateScript);
    webkit_user_content_manager_register_script_message_handler(m_userContentManager, stateHandler, QtWpeWebKit::internalWorld);
    profile->scripts()->addManager(m_userContentManager);
    profile->m_contentFilter->addManager(m_userContentManager);
    g_object_set_data(G_OBJECT(m_webView), pageKey, this);
    QtWpeWebKit::RequestInterception::instance().addPage(this);
    g_signal_connect_swapped(m_webView, "notify::page-id", G_CALLBACK(+[](QWebEnginePage* page) {
        QtWpeWebKit::RequestInterception::instance().addPage(page);
    }), this);
    WebViewSignals::connect(this);
    connectRequestSignals();
}

QWebEnginePage::~QWebEnginePage()
{
    setInspectedPage(nullptr);
    setDevToolsPage(nullptr);
    g_clear_object(&m_inspectorView);
    setSpellingGuesses({});
    m_webChannelTransport.reset();
    QtWpeWebKit::RequestInterception::instance().removePage(this);
    denyPermissionRequests();
    m_profile->scripts()->removeManager(m_userContentManager);
    m_profile->m_contentFilter->removeManager(m_userContentManager);
    g_signal_handlers_disconnect_by_data(m_userContentManager, this);
    g_object_unref(m_userContentManager);
    webkit_user_script_unref(m_stateScript);
    g_signal_handlers_disconnect_by_data(webkit_web_view_get_find_controller(m_webView), this);
    g_signal_handlers_disconnect_by_data(m_webView, this);
    g_object_set_data(G_OBJECT(m_webView), pageKey, nullptr);
    g_object_unref(m_webView);
}

QAction* QWebEnginePage::action(WebAction action) const
{
    static const QHash<WebAction, const char*> texts {
        { Back, "Back" }, { Forward, "Forward" }, { Stop, "Stop" }, { Reload, "Reload" },
        { Cut, "Cut" }, { Copy, "Copy" }, { Paste, "Paste" }, { Undo, "Undo" }, { Redo, "Redo" },
        { SelectAll, "Select All" }, { ReloadAndBypassCache, "Reload and Bypass Cache" },
    };
    QAction*& item = m_actions[action];
    if (!item) {
        auto* self = const_cast<QWebEnginePage*>(this);
        item = new QAction(QString::fromLatin1(texts.value(action, "")), self);
        connect(item, &QAction::triggered, self, [self, action](bool checked) { self->triggerAction(action, checked); });
    }
    return item;
}

void QWebEnginePage::triggerAction(WebAction action, bool)
{
    static const QHash<WebAction, const char*> editingCommands {
        { Cut, WEBKIT_EDITING_COMMAND_CUT }, { Copy, WEBKIT_EDITING_COMMAND_COPY },
        { Paste, WEBKIT_EDITING_COMMAND_PASTE }, { Undo, WEBKIT_EDITING_COMMAND_UNDO },
        { Redo, WEBKIT_EDITING_COMMAND_REDO }, { SelectAll, WEBKIT_EDITING_COMMAND_SELECT_ALL },
    };
    switch (action) {
    case Back:
        webkit_web_view_go_back(m_webView);
        break;
    case Forward:
        webkit_web_view_go_forward(m_webView);
        break;
    case Stop:
        webkit_web_view_stop_loading(m_webView);
        break;
    case Reload:
        webkit_web_view_reload(m_webView);
        break;
    case ReloadAndBypassCache:
        webkit_web_view_reload_bypass_cache(m_webView);
        break;
    case ExitFullScreen:
        setFullScreen(m_webView, false);
        break;
    case RequestClose:
        webkit_web_view_try_close(m_webView);
        break;
    case DownloadLinkToDisk:
        if (m_view)
            downloadAs(m_view->lastContextMenuRequest()->linkUrl());
        break;
    case DownloadImageToDisk:
    case DownloadMediaToDisk:
        if (m_view)
            downloadAs(m_view->lastContextMenuRequest()->mediaUrl());
        break;
    // A save-as download of the page, which the request turns into an archive of the page as shown
    case SavePage:
        downloadAs(url());
        break;
    default:
        if (const char* command = editingCommands.value(action))
            webkit_web_view_execute_editing_command(m_webView, command);
    }
}

void QWebEnginePage::findText(const QString& subString, FindFlags options,
    const std::function<void(const QWebEngineFindTextResult&)>& resultCallback)
{
    auto* finder = webkit_web_view_get_find_controller(m_webView);
    m_findCallback = resultCallback;
    const bool backward = options.testFlag(FindBackward);
    const bool caseSensitive = options.testFlag(FindCaseSensitively);
    if (subString.isEmpty()) {
        m_findText.clear();
        webkit_find_controller_search_finish(finder);
        WebViewSignals::finishFind(this, 0);
    } else if (subString == m_findText && caseSensitive == m_findCaseSensitive) {
        m_findMove = backward ? FindMove::Previous : FindMove::Next;
        backward ? webkit_find_controller_search_previous(finder) : webkit_find_controller_search_next(finder);
    } else {
        m_findText = subString;
        m_findCaseSensitive = caseSensitive;
        m_findMove = backward ? FindMove::Last : FindMove::First;
        guint32 flags = WEBKIT_FIND_OPTIONS_WRAP_AROUND;
        if (!options.testFlag(FindCaseSensitively))
            flags |= WEBKIT_FIND_OPTIONS_CASE_INSENSITIVE;
        if (backward)
            flags |= WEBKIT_FIND_OPTIONS_BACKWARDS;
        webkit_find_controller_search(finder, subString.toUtf8().constData(), flags, G_MAXUINT);
    }
}

bool QWebEnginePage::isLoading() const
{
    return webkit_web_view_is_loading(m_webView);
}

void QWebEnginePage::setInspectedPage(QWebEnginePage* page)
{
    if (m_inspectedPage == page)
        return;
    if (m_inspectedPage) {
        // WPE toggles its inspector: open while this page holds its view
        if (m_inspectorView)
            webkit_web_view_toggle_inspector(m_inspectedPage->m_webView);
        g_clear_object(&m_inspectorView);
        m_inspectedPage->m_devToolsPage = nullptr;
    }
    m_inspectedPage = page;
    if (!page)
        return;
    page->m_devToolsPage = this;
    webkit_settings_set_enable_developer_extras(webkit_web_view_get_settings(page->m_webView), TRUE);
    QtWpeWebKit::adoptNextView([this](WPEView* view) {
        g_set_object(&m_inspectorView, view);
        if (m_view)
            m_view->showView(view);
    });
    webkit_web_view_toggle_inspector(page->m_webView);
}

void QWebEnginePage::setDevToolsPage(QWebEnginePage* devToolsPage)
{
    if (devToolsPage)
        devToolsPage->setInspectedPage(this);
    else if (m_devToolsPage)
        m_devToolsPage->setInspectedPage(nullptr);
}

void QWebEnginePage::javaScriptConsoleMessage(JavaScriptConsoleMessageLevel level, const QString& message,
    int lineNumber, const QString& sourceID)
{
    const QByteArray line = QStringLiteral("%1 (%2:%3)").arg(message, sourceID).arg(lineNumber).toUtf8();
    switch (level) {
    case InfoMessageLevel:
        qCInfo(jsConsole, "%s", line.constData());
        break;
    case WarningMessageLevel:
        qCWarning(jsConsole, "%s", line.constData());
        break;
    case ErrorMessageLevel:
        qCCritical(jsConsole, "%s", line.constData());
        break;
    }
}

void QWebEnginePage::load(const QUrl& url)
{
    m_requestedUrl = url;
    m_loadRequested = true;
    m_errorPageNext = false;
    webkit_web_view_load_uri(m_webView, url.toEncoded().constData());
}

void QWebEnginePage::download(const QUrl& url, const QString&)
{
    g_object_unref(webkit_web_view_download_uri(m_webView, url.toEncoded().constData()));
}

void QWebEnginePage::downloadAs(const QUrl& url)
{
    WebKitDownload* download = webkit_web_view_download_uri(m_webView, url.toEncoded().constData());
    g_object_set_data(G_OBJECT(download), QtWpeWebKit::saveAsKey, GINT_TO_POINTER(TRUE));
    g_object_unref(download);
}

void QWebEnginePage::setHtml(const QString& html, const QUrl& baseUrl)
{
    setContent(html.toUtf8(), QStringLiteral("text/html;charset=UTF-8"), baseUrl);
}

// Without a base URL QtWebEngine loads the content as a data: URL
void QWebEnginePage::setContent(const QByteArray& data, const QString& mimeType, const QUrl& baseUrl)
{
    if (baseUrl.isEmpty()) {
        load(QUrl(QLatin1String("data:") + mimeType + QLatin1String(";base64,") + QLatin1String(data.toBase64())));
        return;
    }
    QStringList parameters = mimeType.split(QLatin1Char(';'));
    const QByteArray type = parameters.takeFirst().trimmed().toUtf8();
    QByteArray charset;
    for (const QString& parameter : std::as_const(parameters)) {
        if (parameter.trimmed().startsWith(QLatin1String("charset="), Qt::CaseInsensitive))
            charset = parameter.section(QLatin1Char('='), 1).trimmed().toUtf8();
    }
    m_requestedUrl = baseUrl;
    m_loadRequested = true;
    m_errorPageNext = false;
    g_autoptr(GBytes) bytes = g_bytes_new(data.constData(), data.size());
    webkit_web_view_load_bytes(m_webView, bytes, type.isEmpty() ? nullptr : type.constData(),
        charset.isEmpty() ? nullptr : charset.constData(), baseUrl.toEncoded().constData());
}

void QWebEnginePage::toHtml(const std::function<void(const QString&)>& resultCallback) const
{
    const_cast<QWebEnginePage*>(this)->runJavaScript(QStringLiteral("document.documentElement.outerHTML"), 0,
        [resultCallback](const QVariant& html) { resultCallback(html.toString()); });
}

void QWebEnginePage::toPlainText(const std::function<void(const QString&)>& resultCallback) const
{
    const_cast<QWebEnginePage*>(this)->runJavaScript(QStringLiteral("document.body.innerText"), 0,
        [resultCallback](const QVariant& text) { resultCallback(text.toString()); });
}

void QWebEnginePage::updateTitle(const QString& pageTitle)
{
    const QString title = pageTitle.isEmpty() ? untitledPageTitle(url()) : pageTitle;
    if (title != m_title)
        Q_EMIT titleChanged(m_title = title);
}

// WebKit tells a new title a task after the page sets it, often after the load's end: the page is asked first
void QWebEnginePage::finishLoad()
{
    const bool blocked = m_mainFrameBlocked.exchange(false);
    m_loadSucceeded = !m_loadFailed && !blocked;
    evaluate(this, "document.title", QtWpeWebKit::internalWorld, [this, load = m_loadCount](JSCValue* title) {
        if (load != m_loadCount)
            return;
        g_autofree char* text = title && jsc_value_is_string(title) ? jsc_value_to_string(title) : nullptr;
        updateTitle(QString::fromUtf8(text ? text : webkit_web_view_get_title(m_webView)));
        emitLoadFinished();
    });
}

void QWebEnginePage::redirectLoad(const QUrl& url)
{
    m_redirecting = true;
    m_requestedUrl = url;
    webkit_web_view_load_uri(m_webView, url.toEncoded().constData());
}

void QWebEnginePage::emitLoadFinished()
{
    if (const std::optional<bool> ok = std::exchange(m_loadSucceeded, std::nullopt))
        Q_EMIT loadFinished(*ok);
}

QUrl QWebEnginePage::url() const
{
    return QUrl::fromEncoded(webkit_web_view_get_uri(m_webView));
}

QIcon QWebEnginePage::icon() const
{
    WebKitImageList* icons = webkit_web_view_get_page_icons(m_webView);
    if (!icons || !webkit_image_list_get_length(icons))
        return {};
    WebKitImage* image = webkit_image_list_get(icons, 0);
    g_autoptr(GBytes) bytes = webkit_image_as_bytes(image);
    // WebKit's pixels are premultiplied BGRA, which is Qt's ARGB32 in memory on little-endian machines
    const QImage pixels(static_cast<const uchar*>(g_bytes_get_data(bytes, nullptr)), webkit_image_get_width(image),
        webkit_image_get_height(image), webkit_image_get_stride(image), QImage::Format_ARGB32_Premultiplied);
    return QIcon(QPixmap::fromImage(pixels.copy()));
}

qreal QWebEnginePage::zoomFactor() const
{
    return webkit_web_view_get_zoom_level(m_webView);
}

void QWebEnginePage::setZoomFactor(qreal factor)
{
    const qreal minimumZoom = 0.25;
    const qreal maximumZoom = 5.0;
    if (factor < minimumZoom || factor > maximumZoom)
        return;
    webkit_web_view_set_zoom_level(m_webView, factor);
    Q_EMIT zoomFactorChanged(factor);
}

void QWebEnginePage::runJavaScript(const QString& scriptSource, quint32 worldId,
    const std::function<void(const QVariant&)>& resultCallback)
{
    const QByteArray world = QtWpeWebKit::worldName(worldId);
    keepWorld(world);
    evaluate(this, scriptSource.toUtf8(), world, [resultCallback](JSCValue* value) {
        if (resultCallback)
            resultCallback(variantOf(value));
    });
}

void QWebEnginePage::setWebChannel(QWebChannel* channel, quint32 worldId)
{
    if (m_webChannel)
        m_webChannel->disconnectFrom(m_webChannelTransport.get());
    m_webChannelTransport.reset();
    m_webChannel = channel;
    if (!channel)
        return;
    m_webChannelTransport = std::make_unique<QtWpeWebKit::WebChannelTransport>(m_webView, m_userContentManager, worldId);
    channel->connectTo(m_webChannelTransport.get());
}

void QWebEnginePage::setBackgroundColor(const QColor& color)
{
    m_backgroundColor = color;
    WebKitColor webKitColor { color.redF(), color.greenF(), color.blueF(), color.alphaF() };
    webkit_web_view_set_background_color(m_webView, &webKitColor);
}

bool QWebEnginePage::isAudioMuted() const
{
    return webkit_web_view_get_is_muted(m_webView);
}

void QWebEnginePage::setAudioMuted(bool muted)
{
    webkit_web_view_set_is_muted(m_webView, muted);
}

bool QWebEnginePage::recentlyAudible() const
{
    return webkit_web_view_is_playing_audio(m_webView);
}

QStringList QWebEnginePage::chooseFiles(FileSelectionMode, const QStringList&, const QStringList&)
{
    return {};
}

void QWebEnginePage::javaScriptAlert(const QUrl&, const QString&)
{
}

bool QWebEnginePage::javaScriptConfirm(const QUrl&, const QString&)
{
    return false;
}

bool QWebEnginePage::javaScriptPrompt(const QUrl&, const QString&, const QString&, QString*)
{
    return false;
}

void QWebEngineNewWindowRequest::openIn(QWebEnginePage* page)
{
    if (m_opener && page->m_openerView == m_opener && !m_openedPage) {
        m_openedPage = page;
        return;
    }
    page->load(m_requestedUrl);
}

void QWebEnginePage::setSpellingGuesses(QList<QPair<QString, GAction*>> guesses)
{
    for (const auto& guess : std::as_const(m_spellingGuesses))
        g_object_unref(guess.second);
    m_spellingGuesses = std::move(guesses);
}

// A suggestion of the last menu replaces the word as WebKit's own menu would; any other word is typed over it
void QWebEnginePage::replaceMisspelledWord(const QString& replacement)
{
    for (const auto& [word, action] : std::as_const(m_spellingGuesses)) {
        if (word == replacement) {
            g_action_activate(action, nullptr);
            return;
        }
    }
    const QByteArray text = QJsonDocument(QJsonArray { replacement }).toJson(QJsonDocument::Compact);
    evaluate(this, "document.execCommand('insertText', false, " + text.mid(1, text.size() - 2) + ")",
        QtWpeWebKit::internalWorld, {});
}

void QWebEnginePage::selectWordAt(QPoint position, const std::function<void(const QString&)>& selected)
{
    static const char script[] = R"((() => {
        const caret = document.caretRangeFromPoint(%1, %2);
        if (!caret || caret.startContainer.nodeType !== Node.TEXT_NODE)
            return '';
        const text = caret.startContainer.data, letter = /[\p{L}\p{M}\p{N}'’]/u;
        let start = caret.startOffset, end = start;
        while (start > 0 && letter.test(text[start - 1]))
            --start;
        while (end < text.length && letter.test(text[end]))
            ++end;
        getSelection().setBaseAndExtent(caret.startContainer, start, caret.startContainer, end);
        return text.slice(start, end);
    })())";
    evaluate(this, QString::fromLatin1(script).arg(position.x()).arg(position.y()).toUtf8(), QtWpeWebKit::internalWorld,
        [selected](JSCValue* word) { selected(variantOf(word).toString()); });
}
