#include "platform.h"

#include "webwidget.h"

#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <QCursor>
#include <QGuiApplication>
#include <QHash>
#include <QOpenGLContext>
#include <QScreen>
#include <wpe/webkit.h>

#ifndef EGL_DRM_RENDER_NODE_FILE_EXT
#define EGL_DRM_RENDER_NODE_FILE_EXT 0x3377
#endif

struct _QtWpeWebKitDisplay {
    WPEDisplay parent;
    EGLDisplay egl;
    WPEDRMDevice* drm;
    QHash<QScreen*, WPEScreen*>* screens; // Qt's, as pages see them
};
G_DEFINE_FINAL_TYPE(QtWpeWebKitDisplay, qtwpewebkit_display, WPE_TYPE_DISPLAY)

G_DECLARE_FINAL_TYPE(QtWpeWebKitScreen, qtwpewebkit_screen, QTWPEWEBKIT, SCREEN, WPEScreen)
struct _QtWpeWebKitScreen {
    WPEScreen parent;
};
G_DEFINE_FINAL_TYPE(QtWpeWebKitScreen, qtwpewebkit_screen, WPE_TYPE_SCREEN)
static void qtwpewebkit_screen_class_init(QtWpeWebKitScreenClass*) {}
static void qtwpewebkit_screen_init(QtWpeWebKitScreen*) {}

struct _QtWpeWebKitToplevel {
    WPEToplevel parent;
};
G_DEFINE_FINAL_TYPE(QtWpeWebKitToplevel, qtwpewebkit_toplevel, WPE_TYPE_TOPLEVEL)

struct _QtWpeWebKitView {
    WPEView parent;
    QtWpeWebKit::WebWidget* widget;
    WPEInputMethodContext* inputMethod; // WebKit's
};
G_DEFINE_FINAL_TYPE(QtWpeWebKitView, qtwpewebkit_view, WPE_TYPE_VIEW)

// Qt's input method speaks for WebKit's: Qt sends text, WebKit tells where the focused field is
struct _QtWpeWebKitInputMethodContext {
    WPEInputMethodContext parent;
    char* preedit;
    guint preeditCursor;
};
G_DEFINE_FINAL_TYPE(QtWpeWebKitInputMethodContext, qtwpewebkit_input_method_context, WPE_TYPE_INPUT_METHOD_CONTEXT)

// The GPU behind Qt's EGL display, so WebKit renders where Qt composites
static WPEDRMDevice* drmDeviceOf(EGLDisplay display)
{
    auto queryDisplay = reinterpret_cast<PFNEGLQUERYDISPLAYATTRIBEXTPROC>(
        eglGetProcAddress("eglQueryDisplayAttribEXT"));
    auto queryDevice = reinterpret_cast<PFNEGLQUERYDEVICESTRINGEXTPROC>(
        eglGetProcAddress("eglQueryDeviceStringEXT"));
    EGLAttrib device = 0;
    if (!queryDisplay || !queryDevice || !queryDisplay(display, EGL_DEVICE_EXT, &device))
        return nullptr;
    auto* eglDevice = reinterpret_cast<EGLDeviceEXT>(device);
    const char* primary = queryDevice(eglDevice, EGL_DRM_DEVICE_FILE_EXT);
    const char* render = queryDevice(eglDevice, EGL_DRM_RENDER_NODE_FILE_EXT);
    return primary ? wpe_drm_device_new(primary, render) : nullptr;
}

static void updateScreen(WPEScreen* screen, QScreen* qscreen)
{
    const QRect geometry = qscreen->geometry();
    const QSizeF millimetres = qscreen->physicalSize();
    constexpr double millihertzPerHertz = 1000;
    wpe_screen_set_position(screen, geometry.x(), geometry.y());
    wpe_screen_set_size(screen, geometry.width(), geometry.height());
    wpe_screen_set_physical_size(screen, qRound(millimetres.width()), qRound(millimetres.height()));
    wpe_screen_set_scale(screen, qscreen->devicePixelRatio());
    wpe_screen_set_refresh_rate(screen, qRound(qscreen->refreshRate() * millihertzPerHertz));
}

static void addScreen(QtWpeWebKitDisplay* display, QScreen* qscreen)
{
    static guint32 lastId;
    auto* screen = WPE_SCREEN(g_object_new(qtwpewebkit_screen_get_type(), "id", ++lastId, nullptr));
    updateScreen(screen, qscreen);
    display->screens->insert(qscreen, screen);
    auto update = [screen, qscreen] { updateScreen(screen, qscreen); };
    QObject::connect(qscreen, &QScreen::geometryChanged, qscreen, update);
    QObject::connect(qscreen, &QScreen::physicalSizeChanged, qscreen, update);
    QObject::connect(qscreen, &QScreen::refreshRateChanged, qscreen, update);
    wpe_display_screen_added(WPE_DISPLAY(display), screen);
}

static void removeScreen(QtWpeWebKitDisplay* display, QScreen* qscreen)
{
    if (WPEScreen* screen = display->screens->take(qscreen)) {
        wpe_display_screen_removed(WPE_DISPLAY(display), screen);
        g_object_unref(screen);
    }
}

static gboolean displayConnect(WPEDisplay* display, GError** error)
{
    auto* context = QOpenGLContext::globalShareContext();
    auto* egl = context ? context->nativeInterface<QNativeInterface::QEGLContext>() : nullptr;
    if (!egl) {
        g_set_error_literal(error, WPE_DISPLAY_ERROR, WPE_DISPLAY_ERROR_CONNECTION_FAILED,
            "Qt has no shared EGL context: set Qt::AA_ShareOpenGLContexts before QApplication");
        return FALSE;
    }
    auto* self = QTWPEWEBKIT_DISPLAY(display);
    self->egl = egl->display();
    self->drm = drmDeviceOf(self->egl);
    self->screens = new QHash<QScreen*, WPEScreen*>;
    for (QScreen* screen : QGuiApplication::screens())
        addScreen(self, screen);
    QObject::connect(qApp, &QGuiApplication::screenAdded, qApp, [self](QScreen* screen) { addScreen(self, screen); });
    QObject::connect(qApp, &QGuiApplication::screenRemoved, qApp, [self](QScreen* screen) { removeScreen(self, screen); });
    return TRUE;
}

static guint displayGetNScreens(WPEDisplay* display)
{
    return QTWPEWEBKIT_DISPLAY(display)->screens->size();
}

static WPEScreen* displayGetScreen(WPEDisplay* display, guint index)
{
    const QList<QScreen*> screens = QGuiApplication::screens();
    return index < guint(screens.size()) ? QTWPEWEBKIT_DISPLAY(display)->screens->value(screens[index]) : nullptr;
}

static std::function<void(WPEView*)> nextViewAdopter;

void QtWpeWebKit::adoptNextView(std::function<void(WPEView*)> adopt)
{
    nextViewAdopter = std::move(adopt);
}

static WPEView* displayCreateView(WPEDisplay* display)
{
    auto* view = WPE_VIEW(g_object_new(QTWPEWEBKIT_TYPE_VIEW, "display", display, nullptr));
    auto* toplevel = WPE_TOPLEVEL(g_object_new(QTWPEWEBKIT_TYPE_TOPLEVEL, "display", display, nullptr));
    wpe_view_set_toplevel(view, toplevel);
    g_object_unref(toplevel);
    if (auto adopt = std::exchange(nextViewAdopter, nullptr))
        adopt(view);
    return view;
}

static WPEInputMethodContext* displayCreateInputMethodContext(WPEDisplay*, WPEView* view)
{
    auto* context = WPE_INPUT_METHOD_CONTEXT(g_object_new(QTWPEWEBKIT_TYPE_INPUT_METHOD_CONTEXT, "view", view, nullptr));
    QTWPEWEBKIT_VIEW(view)->inputMethod = context;
    g_object_add_weak_pointer(G_OBJECT(context), reinterpret_cast<gpointer*>(&QTWPEWEBKIT_VIEW(view)->inputMethod));
    return context;
}

static gpointer displayGetEGLDisplay(WPEDisplay* display, GError**)
{
    return QTWPEWEBKIT_DISPLAY(display)->egl;
}

static WPEDRMDevice* displayGetDRMDevice(WPEDisplay* display)
{
    return QTWPEWEBKIT_DISPLAY(display)->drm;
}

static void displayFinalize(GObject* object)
{
    auto* self = QTWPEWEBKIT_DISPLAY(object);
    g_clear_pointer(&self->drm, wpe_drm_device_unref);
    if (self->screens) {
        for (WPEScreen* screen : std::as_const(*self->screens))
            g_object_unref(screen);
        delete self->screens;
    }
    G_OBJECT_CLASS(qtwpewebkit_display_parent_class)->finalize(object);
}

static void qtwpewebkit_display_class_init(QtWpeWebKitDisplayClass* klass)
{
    G_OBJECT_CLASS(klass)->finalize = displayFinalize;
    auto* displayClass = WPE_DISPLAY_CLASS(klass);
    displayClass->connect = displayConnect;
    displayClass->create_view = displayCreateView;
    displayClass->get_egl_display = displayGetEGLDisplay;
    displayClass->get_drm_device = displayGetDRMDevice;
    displayClass->create_input_method_context = displayCreateInputMethodContext;
    displayClass->get_n_screens = displayGetNScreens;
    displayClass->get_screen = displayGetScreen;
}

static void qtwpewebkit_display_init(QtWpeWebKitDisplay*) {}

// A toplevel's size is its one view's
static gboolean toplevelResize(WPEToplevel* toplevel, int width, int height)
{
    int size[] = { width, height };
    // a widget's view takes the widget's size, whatever WebKit asks, as for its inspector's window
    wpe_toplevel_foreach_view(
        toplevel,
        [](WPEToplevel*, WPEView* view, gpointer data) -> gboolean {
            auto* widget = QTWPEWEBKIT_VIEW(view)->widget;
            if (widget && !widget->size().isEmpty()) {
                auto* wh = static_cast<int*>(data);
                wh[0] = widget->width();
                wh[1] = widget->height();
            }
            return FALSE;
        },
        size);
    wpe_toplevel_resized(toplevel, size[0], size[1]);
    wpe_toplevel_foreach_view(
        toplevel,
        [](WPEToplevel*, WPEView* view, gpointer data) -> gboolean {
            auto* wh = static_cast<int*>(data);
            wpe_view_resized(view, wh[0], wh[1]);
            return FALSE;
        },
        size);
    return TRUE;
}

// The screen its view's widget is on, the primary one while it is on none
static WPEScreen* toplevelGetScreen(WPEToplevel* toplevel)
{
    QScreen* qscreen = QGuiApplication::primaryScreen();
    wpe_toplevel_foreach_view(
        toplevel,
        [](WPEToplevel*, WPEView* view, gpointer data) -> gboolean {
            if (auto* widget = QTWPEWEBKIT_VIEW(view)->widget)
                *static_cast<QScreen**>(data) = widget->screen();
            return TRUE;
        },
        &qscreen);
    auto* display = QTWPEWEBKIT_DISPLAY(wpe_toplevel_get_display(toplevel));
    return display && display->screens ? display->screens->value(qscreen) : nullptr;
}

static void qtwpewebkit_toplevel_class_init(QtWpeWebKitToplevelClass* klass)
{
    WPE_TOPLEVEL_CLASS(klass)->resize = toplevelResize;
    WPE_TOPLEVEL_CLASS(klass)->get_screen = toplevelGetScreen;
}

static void qtwpewebkit_toplevel_init(QtWpeWebKitToplevel*) {}

static gboolean viewRenderBuffer(WPEView* view, WPEBuffer* buffer, const WPERectangle*, guint, GError**)
{
    if (auto* widget = QTWPEWEBKIT_VIEW(view)->widget)
        widget->presentBuffer(buffer);
    else {
        wpe_view_buffer_rendered(view, buffer);
        wpe_view_buffer_released(view, buffer);
    }
    return TRUE;
}

static void viewSetCursorFromName(WPEView* view, const char* name)
{
    static const QHash<QByteArray, Qt::CursorShape> shapes {
        { "default", Qt::ArrowCursor }, { "pointer", Qt::PointingHandCursor },
        { "text", Qt::IBeamCursor }, { "vertical-text", Qt::IBeamCursor },
        { "wait", Qt::WaitCursor }, { "progress", Qt::BusyCursor },
        { "help", Qt::WhatsThisCursor }, { "crosshair", Qt::CrossCursor },
        { "move", Qt::SizeAllCursor }, { "grab", Qt::OpenHandCursor },
        { "grabbing", Qt::ClosedHandCursor }, { "not-allowed", Qt::ForbiddenCursor },
        { "no-drop", Qt::ForbiddenCursor }, { "none", Qt::BlankCursor },
        { "col-resize", Qt::SplitHCursor }, { "row-resize", Qt::SplitVCursor },
        { "ew-resize", Qt::SizeHorCursor }, { "e-resize", Qt::SizeHorCursor },
        { "w-resize", Qt::SizeHorCursor }, { "ns-resize", Qt::SizeVerCursor },
        { "n-resize", Qt::SizeVerCursor }, { "s-resize", Qt::SizeVerCursor },
        { "nesw-resize", Qt::SizeBDiagCursor }, { "ne-resize", Qt::SizeBDiagCursor },
        { "sw-resize", Qt::SizeBDiagCursor }, { "nwse-resize", Qt::SizeFDiagCursor },
        { "nw-resize", Qt::SizeFDiagCursor }, { "se-resize", Qt::SizeFDiagCursor },
    };
    if (auto* widget = QTWPEWEBKIT_VIEW(view)->widget)
        widget->setCursor(shapes.value(name, Qt::ArrowCursor));
}

// The context may outlive its view
static void viewDispose(GObject* object)
{
    auto* self = QTWPEWEBKIT_VIEW(object);
    if (self->inputMethod)
        g_object_remove_weak_pointer(G_OBJECT(self->inputMethod), reinterpret_cast<gpointer*>(&self->inputMethod));
    self->inputMethod = nullptr;
    G_OBJECT_CLASS(qtwpewebkit_view_parent_class)->dispose(object);
}

static void qtwpewebkit_view_class_init(QtWpeWebKitViewClass* klass)
{
    G_OBJECT_CLASS(klass)->dispose = viewDispose;
    auto* viewClass = WPE_VIEW_CLASS(klass);
    viewClass->render_buffer = viewRenderBuffer;
    viewClass->set_cursor_from_name = viewSetCursorFromName;
}

static void qtwpewebkit_view_init(QtWpeWebKitView*) {}

static QtWpeWebKit::WebWidget* widgetOf(WPEInputMethodContext* context)
{
    WPEView* view = wpe_input_method_context_get_view(context);
    return view ? QTWPEWEBKIT_VIEW(view)->widget : nullptr;
}

static void inputMethodGetPreedit(WPEInputMethodContext* context, char** text, GList** underlines, guint* cursor)
{
    auto* self = QTWPEWEBKIT_INPUT_METHOD_CONTEXT(context);
    if (text)
        *text = g_strdup(self->preedit ? self->preedit : "");
    if (underlines)
        *underlines = nullptr;
    if (cursor)
        *cursor = self->preeditCursor;
}

// WebKit's focus is on a field that takes text, or has left it
static void inputMethodFocusIn(WPEInputMethodContext* context)
{
    if (auto* widget = widgetOf(context))
        widget->setInputMethodEnabled(true);
}

static void inputMethodFocusOut(WPEInputMethodContext* context)
{
    if (auto* widget = widgetOf(context))
        widget->setInputMethodEnabled(false);
}

static void inputMethodSetCursorArea(WPEInputMethodContext* context, int x, int y, int width, int height)
{
    if (auto* widget = widgetOf(context))
        widget->setInputMethodCursorArea(QRect(x, y, width, height));
}

// WebKit counts in UTF-8 bytes
static void inputMethodSetSurrounding(WPEInputMethodContext* context, const char* text, guint length, guint cursor, guint anchor)
{
    auto* widget = widgetOf(context);
    if (!widget)
        return;
    const QByteArray utf8(text, length);
    widget->setSurroundingText(QString::fromUtf8(utf8), QString::fromUtf8(utf8.left(cursor)).size(),
        QString::fromUtf8(utf8.left(anchor)).size());
}

static void inputMethodReset(WPEInputMethodContext* context)
{
    if (auto* widget = widgetOf(context))
        widget->resetInputMethod();
}

static void inputMethodFinalize(GObject* object)
{
    g_free(QTWPEWEBKIT_INPUT_METHOD_CONTEXT(object)->preedit);
    G_OBJECT_CLASS(qtwpewebkit_input_method_context_parent_class)->finalize(object);
}

static void qtwpewebkit_input_method_context_class_init(QtWpeWebKitInputMethodContextClass* klass)
{
    G_OBJECT_CLASS(klass)->finalize = inputMethodFinalize;
    auto* contextClass = WPE_INPUT_METHOD_CONTEXT_CLASS(klass);
    contextClass->get_preedit_string = inputMethodGetPreedit;
    contextClass->focus_in = inputMethodFocusIn;
    contextClass->focus_out = inputMethodFocusOut;
    contextClass->set_cursor_area = inputMethodSetCursorArea;
    contextClass->set_surrounding = inputMethodSetSurrounding;
    contextClass->reset = inputMethodReset;
}

static void qtwpewebkit_input_method_context_init(QtWpeWebKitInputMethodContext*) {}

namespace QtWpeWebKit {

WPEDisplay* display()
{
    static WPEDisplay* display = [] {
        auto* display = WPE_DISPLAY(g_object_new(QTWPEWEBKIT_TYPE_DISPLAY, nullptr));
        GError* error = nullptr;
        if (!wpe_display_connect(display, &error))
            qFatal("QtWpeWebKit: %s", error->message);
        return display;
    }();
    return display;
}

void setViewWidget(WPEView* view, WebWidget* widget)
{
    QTWPEWEBKIT_VIEW(view)->widget = widget;
}

bool showsErrorPage(const GError* error)
{
    return !g_error_matches(error, WEBKIT_NETWORK_ERROR, WEBKIT_NETWORK_ERROR_CANCELLED)
        && !g_error_matches(error, WEBKIT_MEDIA_ERROR, WEBKIT_MEDIA_ERROR_WILL_HANDLE_LOAD)
        && !g_error_matches(error, WEBKIT_POLICY_ERROR, WEBKIT_POLICY_ERROR_FRAME_LOAD_INTERRUPTED_BY_POLICY_CHANGE);
}

void commitText(WPEView* view, const QString& text)
{
    if (auto* context = QTWPEWEBKIT_VIEW(view)->inputMethod)
        g_signal_emit_by_name(context, "committed", text.toUtf8().constData());
}

void deleteSurroundingText(WPEView* view, int offset, int length)
{
    if (auto* context = QTWPEWEBKIT_VIEW(view)->inputMethod)
        g_signal_emit_by_name(context, "delete-surrounding", offset, guint(length));
}

void setPreeditText(WPEView* view, const QString& text, int cursor)
{
    auto* context = QTWPEWEBKIT_VIEW(view)->inputMethod;
    if (!context)
        return;
    auto* self = QTWPEWEBKIT_INPUT_METHOD_CONTEXT(context);
    const bool wasEmpty = !self->preedit || !*self->preedit;
    if (wasEmpty && text.isEmpty())
        return;
    g_free(self->preedit);
    self->preedit = g_strdup(text.toUtf8().constData());
    self->preeditCursor = cursor;
    if (wasEmpty)
        g_signal_emit_by_name(context, "preedit-started");
    g_signal_emit_by_name(context, "preedit-changed");
    if (text.isEmpty())
        g_signal_emit_by_name(context, "preedit-finished");
}

Qt::InputMethodHints inputHintsOf(WPEView* view)
{
    auto* context = QTWPEWEBKIT_VIEW(view)->inputMethod;
    if (!context)
        return Qt::ImhNone;
    const Qt::InputMethodHints hidden = Qt::ImhHiddenText | Qt::ImhSensitiveData | Qt::ImhNoPredictiveText;
    switch (wpe_input_method_context_get_input_purpose(context)) {
    case WPE_INPUT_PURPOSE_DIGITS:
        return Qt::ImhDigitsOnly;
    case WPE_INPUT_PURPOSE_NUMBER:
        return Qt::ImhFormattedNumbersOnly;
    case WPE_INPUT_PURPOSE_PHONE:
        return Qt::ImhDialableCharactersOnly;
    case WPE_INPUT_PURPOSE_URL:
        return Qt::ImhUrlCharactersOnly;
    case WPE_INPUT_PURPOSE_EMAIL:
        return Qt::ImhEmailCharactersOnly;
    case WPE_INPUT_PURPOSE_PASSWORD:
        return hidden;
    case WPE_INPUT_PURPOSE_PIN:
        return hidden | Qt::ImhDigitsOnly;
    default:
        return Qt::ImhNone;
    }
}

} // namespace QtWpeWebKit
