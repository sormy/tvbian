#include "webwidget.h"

#include "keyboard.h"
#include "platform.h"

#include <EGL/egl.h>
#include <cstring>
#include <QGuiApplication>
#include <QInputMethod>
#include <QInputMethodEvent>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QWheelEvent>
#include <QWindow>
#include <wpe/webkit.h>

namespace QtWpeWebKit {

// QWheelEvent's angleDelta per notch of a mouse wheel
constexpr qreal wheelUnitsPerTick = 120;

// glEGLImageTargetTexture2DOES, from GL_OES_EGL_image
using ImageTargetTexture2D = void (*)(GLenum target, void* image);
static ImageTargetTexture2D imageTargetTexture2D;

// One full-widget quad; the buffer's first row is the page's top
static const char* vertexShader = R"(
attribute vec2 position;
varying vec2 texCoord;
void main() {
    texCoord = vec2(position.x + 1.0, 1.0 - position.y) * 0.5;
    gl_Position = vec4(position, 0.0, 1.0);
})";
static const char* fragmentShader = R"(
#ifdef GL_ES
precision mediump float;
#endif
varying vec2 texCoord;
uniform sampler2D page;
uniform bool swapRedBlue;
void main() {
    vec4 color = texture2D(page, texCoord);
    gl_FragColor = swapRedBlue ? color.bgra : color;
})";
static const GLfloat quad[] = { -1, -1, 1, -1, -1, 1, 1, 1 };

static guint32 pointerButtonModifiers(Qt::MouseButtons buttons)
{
    guint32 modifiers = 0;
    if (buttons & Qt::LeftButton)
        modifiers |= WPE_MODIFIER_POINTER_BUTTON1;
    if (buttons & Qt::MiddleButton)
        modifiers |= WPE_MODIFIER_POINTER_BUTTON2;
    if (buttons & Qt::RightButton)
        modifiers |= WPE_MODIFIER_POINTER_BUTTON3;
    return modifiers;
}

static guint32 keyboardModifiers(Qt::KeyboardModifiers qt)
{
    guint32 modifiers = 0;
    if (qt & Qt::ShiftModifier)
        modifiers |= WPE_MODIFIER_KEYBOARD_SHIFT;
    if (qt & Qt::ControlModifier)
        modifiers |= WPE_MODIFIER_KEYBOARD_CONTROL;
    if (qt & Qt::AltModifier)
        modifiers |= WPE_MODIFIER_KEYBOARD_ALT;
    if (qt & Qt::MetaModifier)
        modifiers |= WPE_MODIFIER_KEYBOARD_META;
    return modifiers;
}

static WPEModifiers modifiersOf(const QSinglePointEvent* event)
{
    return static_cast<WPEModifiers>(pointerButtonModifiers(event->buttons()) | keyboardModifiers(event->modifiers()));
}

static guint buttonOf(Qt::MouseButton button)
{
    switch (button) {
    case Qt::LeftButton:
        return WPE_BUTTON_PRIMARY;
    case Qt::MiddleButton:
        return WPE_BUTTON_MIDDLE;
    case Qt::RightButton:
        return WPE_BUTTON_SECONDARY;
    default:
        return 0;
    }
}

static void dispatch(WPEView* view, WPEEvent* event)
{
    wpe_view_event(view, event);
    wpe_event_unref(event);
}

WebWidget::WebWidget(QWidget* parent)
    : WebWidget(WEBKIT_WEB_VIEW(g_object_new(WEBKIT_TYPE_WEB_VIEW, "display", display(), nullptr)), parent)
{
    g_object_unref(m_webView);
}

WebWidget::WebWidget(WPEView* view, QWidget* parent)
    : QOpenGLWidget(parent)
    , m_view(WPE_VIEW(g_object_ref(view)))
{
    setFocusPolicy(Qt::StrongFocus);
    setMouseTracking(true);
    setViewWidget(m_view, this);
    toplevelChanged();
    // WebKit takes its inspector's view off its toplevel and gives it back later
    g_signal_connect_swapped(m_view, "notify::toplevel", G_CALLBACK(+[](WebWidget* self) {
        self->toplevelChanged();
    }), this);
    connect(this, &QOpenGLWidget::frameSwapped, this, &WebWidget::frameShown);
}

void WebWidget::toplevelChanged()
{
    auto* toplevel = wpe_view_get_toplevel(m_view);
    if (!toplevel)
        return;
    wpe_toplevel_state_changed(toplevel, WPE_TOPLEVEL_STATE_ACTIVE);
    if (!isVisible())
        return;
    wpe_view_map(m_view);
    resizeGL(width(), height());
}

WebWidget::WebWidget(WebKitWebView* webView, QWidget* parent)
    : WebWidget(webkit_web_view_get_wpe_view(webView), parent)
{
    m_webView = WEBKIT_WEB_VIEW(g_object_ref(webView));
    g_signal_connect_swapped(m_webView, "notify::title", G_CALLBACK(+[](WebWidget* self) {
        Q_EMIT self->titleChanged(self->title());
    }), this);
    g_signal_connect_swapped(m_webView, "notify::uri", G_CALLBACK(+[](WebWidget* self) {
        Q_EMIT self->urlChanged(self->url());
    }), this);
    g_signal_connect_swapped(m_webView, "notify::estimated-load-progress", G_CALLBACK(+[](WebWidget* self) {
        Q_EMIT self->loadProgress(qRound(100 * webkit_web_view_get_estimated_load_progress(self->m_webView)));
    }), this);
    g_signal_connect(m_webView, "load-changed", G_CALLBACK(+[](WebKitWebView*, WebKitLoadEvent event, WebWidget* self) {
        if (event == WEBKIT_LOAD_STARTED) {
            self->m_loadingErrorPage = std::exchange(self->m_errorPageNext, false);
            if (!self->m_loadingErrorPage)
                self->m_loadFailed = false;
        } else if (event == WEBKIT_LOAD_FINISHED && !std::exchange(self->m_loadingErrorPage, false))
            Q_EMIT self->loadFinished(!self->m_loadFailed);
    }), this);
    // WebKit reports the failure, then the load's end
    g_signal_connect(m_webView, "load-failed", G_CALLBACK(+[](WebKitWebView*, WebKitLoadEvent, char*, GError* error, WebWidget* self) {
        self->m_loadFailed = true;
        self->m_errorPageNext = showsErrorPage(error);
        return FALSE;
    }), this);
}

WebWidget::~WebWidget()
{
    setViewWidget(m_view, nullptr);
    g_signal_handlers_disconnect_by_data(m_view, this);
    if (m_webView)
        g_signal_handlers_disconnect_by_data(m_webView, this);
    if (m_texture) {
        makeCurrent();
        glDeleteTextures(1, &m_texture);
        doneCurrent();
    }
    // The view may outlive this widget: give WebKit its buffers back
    for (WPEBuffer** buffer : { &m_pending, &m_drawn, &m_shown }) {
        if (*buffer)
            wpe_view_buffer_released(wpeView(), *buffer);
        g_clear_object(buffer);
    }
    g_clear_object(&m_webView);
    g_object_unref(m_view);
}

WPEView* WebWidget::wpeView() const
{
    return m_view;
}

void WebWidget::load(const QUrl& url)
{
    m_errorPageNext = false;
    if (m_webView)
        webkit_web_view_load_uri(m_webView, url.toEncoded().constData());
}

QString WebWidget::title() const
{
    return m_webView ? QString::fromUtf8(webkit_web_view_get_title(m_webView)) : QString();
}

QUrl WebWidget::url() const
{
    return m_webView ? QUrl::fromEncoded(webkit_web_view_get_uri(m_webView)) : QUrl();
}

void WebWidget::presentBuffer(WPEBuffer* buffer)
{
    if (m_pending)
        wpe_view_buffer_released(wpeView(), m_pending);
    g_set_object(&m_pending, buffer);
    update();
}

void WebWidget::frameShown()
{
    if (!m_drawn)
        return;
    if (m_shown)
        wpe_view_buffer_released(wpeView(), m_shown);
    g_clear_object(&m_shown);
    m_shown = std::exchange(m_drawn, nullptr);
    wpe_view_buffer_rendered(wpeView(), m_shown);
}

void WebWidget::initializeGL()
{
    initializeOpenGLFunctions();
    if (!imageTargetTexture2D)
        imageTargetTexture2D = reinterpret_cast<ImageTargetTexture2D>(
            eglGetProcAddress("glEGLImageTargetTexture2DOES"));
    glGenTextures(1, &m_texture);
    glBindTexture(GL_TEXTURE_2D, m_texture);
    for (GLenum parameter : { GL_TEXTURE_WRAP_S, GL_TEXTURE_WRAP_T })
        glTexParameteri(GL_TEXTURE_2D, parameter, GL_CLAMP_TO_EDGE);
    for (GLenum parameter : { GL_TEXTURE_MIN_FILTER, GL_TEXTURE_MAG_FILTER })
        glTexParameteri(GL_TEXTURE_2D, parameter, GL_LINEAR);
    m_program.addShaderFromSourceCode(QOpenGLShader::Vertex, vertexShader);
    m_program.addShaderFromSourceCode(QOpenGLShader::Fragment, fragmentShader);
    m_program.bindAttributeLocation("position", 0);
    if (!m_program.link())
        qWarning("QtWpeWebKit: %s", qPrintable(m_program.log()));
}

void WebWidget::paintGL()
{
    glClearColor(1, 1, 1, 1);
    glClear(GL_COLOR_BUFFER_BIT);
    glBindTexture(GL_TEXTURE_2D, m_texture);
    if (m_pending) {
        if (!(WPE_IS_BUFFER_SHM(m_pending) ? uploadPixels(WPE_BUFFER_SHM(m_pending)) : importImage(m_pending)))
            return;
        if (m_drawn)
            wpe_view_buffer_released(wpeView(), m_drawn);
        g_clear_object(&m_drawn);
        m_drawn = std::exchange(m_pending, nullptr);
    } else if (!m_drawn && !m_shown)
        return;
    m_program.bind();
    m_program.setUniformValue("swapRedBlue", m_swapRedBlue);
    m_program.enableAttributeArray(0);
    m_program.setAttributeArray(0, GL_FLOAT, quad, 2);
    glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
    m_program.disableAttributeArray(0);
}

// A GPU frame: the texture becomes the buffer itself
bool WebWidget::importImage(WPEBuffer* buffer)
{
    GError* error = nullptr;
    auto* image = wpe_buffer_import_to_egl_image(buffer, &error);
    if (!image) {
        qWarning("QtWpeWebKit: %s", error->message);
        g_error_free(error);
        return false;
    }
    imageTargetTexture2D(GL_TEXTURE_2D, image);
    m_swapRedBlue = false;
    return true;
}

// A frame WebKit painted without a GPU: ARGB8888, so B,G,R,A in memory, uploaded as RGBA and
// swapped back in the shader; GLES2 cannot skip a row's padding, so padded rows are packed first
bool WebWidget::uploadPixels(WPEBufferSHM* buffer)
{
    const int width = wpe_buffer_get_width(WPE_BUFFER(buffer));
    const int height = wpe_buffer_get_height(WPE_BUFFER(buffer));
    const guint stride = wpe_buffer_shm_get_stride(buffer);
    const guint rowBytes = guint(width) * 4;
    gsize size = 0;
    const auto* pixels = static_cast<const char*>(g_bytes_get_data(wpe_buffer_shm_get_data(buffer), &size));
    if (size < gsize(stride) * height)
        return false;
    QByteArray packed;
    if (stride != rowBytes) {
        packed.resize(qsizetype(rowBytes) * height);
        for (int row = 0; row < height; row++)
            memcpy(packed.data() + qsizetype(row) * rowBytes, pixels + gsize(row) * stride, rowBytes);
        pixels = packed.constData();
    }
    glPixelStorei(GL_UNPACK_ALIGNMENT, 4);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, pixels);
    m_swapRedBlue = true;
    return true;
}

void WebWidget::resizeGL(int, int)
{
    auto* toplevel = wpe_view_get_toplevel(wpeView());
    if (!toplevel)
        return;
    wpe_toplevel_scale_changed(toplevel, devicePixelRatioF());
    wpe_toplevel_resize(toplevel, width(), height());
}

// A hidden tab's page is throttled by WebKit
void WebWidget::showEvent(QShowEvent* event)
{
    wpe_view_map(wpeView());
    if (QWindow* window = this->window()->windowHandle())
        connect(window, &QWindow::screenChanged, this, &WebWidget::screenChanged, Qt::UniqueConnection);
    QOpenGLWidget::showEvent(event);
}

// The page's screen is the window's
void WebWidget::screenChanged()
{
    auto* toplevel = wpe_view_get_toplevel(wpeView());
    wpe_toplevel_screen_changed(toplevel);
    wpe_toplevel_scale_changed(toplevel, devicePixelRatioF());
}

void WebWidget::hideEvent(QHideEvent* event)
{
    wpe_view_unmap(wpeView());
    QOpenGLWidget::hideEvent(event);
}

void WebWidget::focusInEvent(QFocusEvent* event)
{
    wpe_view_focus_in(wpeView());
    QOpenGLWidget::focusInEvent(event);
}

void WebWidget::focusOutEvent(QFocusEvent* event)
{
    wpe_view_focus_out(wpeView());
    QOpenGLWidget::focusOutEvent(event);
}

// WebKit dates an event with no time as it arrives, on its own clock; Qt's times run on another, and a click
// dated off WebKit's clock does not count as the user's activation
static const guint32 stampedOnArrival = 0;

void WebWidget::sendButton(QMouseEvent* event, bool press)
{
    const QPointF position = event->position();
    const guint button = buttonOf(event->button());
    const guint pressCount = press
        ? wpe_view_compute_press_count(wpeView(), position.x(), position.y(), button, event->timestamp())
        : 0;
    dispatch(wpeView(), wpe_event_pointer_button_new(press ? WPE_EVENT_POINTER_DOWN : WPE_EVENT_POINTER_UP,
        wpeView(), WPE_INPUT_SOURCE_MOUSE, stampedOnArrival, modifiersOf(event), button,
        position.x(), position.y(), pressCount));
}

void WebWidget::mousePressEvent(QMouseEvent* event)
{
    sendButton(event, true);
}

// Qt reports a double click's second press as a double click
void WebWidget::mouseDoubleClickEvent(QMouseEvent* event)
{
    sendButton(event, true);
}

void WebWidget::mouseReleaseEvent(QMouseEvent* event)
{
    sendButton(event, false);
}

void WebWidget::mouseMoveEvent(QMouseEvent* event)
{
    const QPointF position = event->position();
    const QPointF delta = position - m_lastPointer;
    m_lastPointer = position;
    dispatch(wpeView(), wpe_event_pointer_move_new(WPE_EVENT_POINTER_MOVE, wpeView(), WPE_INPUT_SOURCE_MOUSE,
        stampedOnArrival, modifiersOf(event), position.x(), position.y(), delta.x(), delta.y()));
}

void WebWidget::wheelEvent(QWheelEvent* event)
{
    const QPointF position = event->position();
    const bool precise = !event->pixelDelta().isNull();
    // WebKit takes wheel ticks when the deltas are not precise
    const QPointF delta = precise ? QPointF(event->pixelDelta()) : event->angleDelta().toPointF() / wheelUnitsPerTick;
    dispatch(wpeView(), wpe_event_scroll_new(wpeView(), WPE_INPUT_SOURCE_MOUSE, stampedOnArrival, modifiersOf(event),
        delta.x(), delta.y(), precise, FALSE, position.x(), position.y()));
}

// WPE takes the hardware keycode and the keysym, both XKB's on Wayland
void WebWidget::sendKey(QKeyEvent* event, bool press)
{
    const guint keyval = keyvalOf(event);
    dispatch(wpeView(), wpe_event_keyboard_new(press ? WPE_EVENT_KEYBOARD_KEY_DOWN : WPE_EVENT_KEYBOARD_KEY_UP,
        wpeView(), WPE_INPUT_SOURCE_KEYBOARD, stampedOnArrival,
        static_cast<WPEModifiers>(keyboardModifiers(event->modifiers())), keycodeOf(event, keyval), keyval));
    Q_EMIT keySent(event);
}

void WebWidget::keyPressEvent(QKeyEvent* event)
{
    sendKey(event, true);
}

void WebWidget::keyReleaseEvent(QKeyEvent* event)
{
    sendKey(event, false);
}

// As QtWebEngine does, the input method, an on-screen keyboard among them, is on while a field has the focus
void WebWidget::setInputMethodEnabled(bool enabled)
{
    setAttribute(Qt::WA_InputMethodEnabled, enabled);
    if (!hasFocus())
        return;
    QInputMethod* inputMethod = QGuiApplication::inputMethod();
    inputMethod->update(Qt::ImEnabled | Qt::ImHints);
    inputMethod->setVisible(enabled);
}

void WebWidget::setInputMethodCursorArea(const QRect& area)
{
    m_inputCursorArea = area;
    if (hasFocus())
        QGuiApplication::inputMethod()->update(Qt::ImCursorRectangle);
}

void WebWidget::setSurroundingText(const QString& text, int cursor, int anchor)
{
    m_surroundingText = text;
    m_inputCursor = cursor;
    m_inputAnchor = anchor;
    if (hasFocus())
        QGuiApplication::inputMethod()->update(Qt::ImSurroundingText | Qt::ImCursorPosition | Qt::ImAnchorPosition);
}

void WebWidget::resetInputMethod()
{
    if (hasFocus())
        QGuiApplication::inputMethod()->reset();
}

void WebWidget::inputMethodEvent(QInputMethodEvent* event)
{
    if (event->replacementLength())
        deleteSurroundingText(wpeView(), event->replacementStart(), event->replacementLength());
    if (!event->commitString().isEmpty())
        commitText(wpeView(), event->commitString());
    int cursor = event->preeditString().size();
    for (const QInputMethodEvent::Attribute& attribute : event->attributes()) {
        if (attribute.type == QInputMethodEvent::Cursor)
            cursor = attribute.start;
    }
    setPreeditText(wpeView(), event->preeditString(), cursor);
    event->accept();
}

QVariant WebWidget::inputMethodQuery(Qt::InputMethodQuery query) const
{
    switch (query) {
    case Qt::ImEnabled:
        return testAttribute(Qt::WA_InputMethodEnabled);
    case Qt::ImHints:
        return int(inputHintsOf(wpeView()));
    case Qt::ImCursorRectangle:
        return m_inputCursorArea;
    case Qt::ImSurroundingText:
        return m_surroundingText;
    case Qt::ImCursorPosition:
        return m_inputCursor;
    case Qt::ImAnchorPosition:
        return m_inputAnchor;
    default:
        return QOpenGLWidget::inputMethodQuery(query);
    }
}

} // namespace QtWpeWebKit
