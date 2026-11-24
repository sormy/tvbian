// A web view as a Qt widget: WebKit's frames drawn without a copy, Qt's input fed to the page
#pragma once

#include <QOpenGLFunctions>
#include <QOpenGLShaderProgram>
#include <QContextMenuEvent>
#include <QOpenGLWidget>
#include <QUrl>
#include <memory>

typedef struct _WebKitWebView WebKitWebView;
typedef struct _WPEBuffer WPEBuffer;
typedef struct _WPEBufferSHM WPEBufferSHM;
typedef struct _WPEView WPEView;

namespace QtWpeWebKit {

class Subsurface;

class WebWidget : public QOpenGLWidget, protected QOpenGLFunctions {
    Q_OBJECT
public:
    explicit WebWidget(QWidget* parent = nullptr);
    // Shows a web view made elsewhere, sharing it
    explicit WebWidget(WebKitWebView* webView, QWidget* parent = nullptr);
    // Shows a view WebKit made with no web view of the API's, as its inspector's
    explicit WebWidget(WPEView* view, QWidget* parent = nullptr);
    ~WebWidget() override;

    WebKitWebView* webView() const { return m_webView; }
    void load(const QUrl& url);
    QString title() const;
    QUrl url() const;

    // A frame from WebKit to show next
    void presentBuffer(WPEBuffer* buffer);

    // What WebKit tells Qt's input method about the page's focused field
    void setInputMethodEnabled(bool enabled);
    void setInputMethodCursorArea(const QRect& area);
    void setSurroundingText(const QString& text, int cursor, int anchor);
    void resetInputMethod();

Q_SIGNALS:
    void titleChanged(const QString& title);
    void urlChanged(const QUrl& url);
    void loadProgress(int percent);
    void loadFinished(bool ok);
    // A key went to the page; WebKit does not tell whether the page used it
    void keySent(QKeyEvent* event);

protected:
    bool event(QEvent* event) override;
    void initializeGL() override;
    void paintGL() override;
    void resizeGL(int width, int height) override;
    void showEvent(QShowEvent* event) override;
    void hideEvent(QHideEvent* event) override;
    void focusInEvent(QFocusEvent* event) override;
    void focusOutEvent(QFocusEvent* event) override;
    void mousePressEvent(QMouseEvent* event) override;
    void mouseDoubleClickEvent(QMouseEvent* event) override;
    void mouseReleaseEvent(QMouseEvent* event) override;
    void mouseMoveEvent(QMouseEvent* event) override;
    void wheelEvent(QWheelEvent* event) override;
    void keyPressEvent(QKeyEvent* event) override;
    void keyReleaseEvent(QKeyEvent* event) override;
    void inputMethodEvent(QInputMethodEvent* event) override;
    QVariant inputMethodQuery(Qt::InputMethodQuery query) const override;
    // The page asks for its context menu, once it has seen the click
    void contextMenuEvent(QContextMenuEvent* event) override { event->accept(); }
    // Tab moves focus inside the page, not between widgets
    bool focusNextPrevChild(bool) override { return false; }

private:
    void screenChanged();
    // The view's toplevel set again: its state, map and size sent to it
    void toplevelChanged();
    WPEView* wpeView() const;
    void sendButton(QMouseEvent* event, bool press);
    void sendKey(QKeyEvent* event, bool press);
    // Qt shows the frame painted last: WebKit may reuse the one before and send the next
    void frameShown();
    bool importImage(WPEBuffer* buffer);
    bool uploadPixels(WPEBufferSHM* buffer);
    // WebKit's buffers this holds, given back to it
    void releaseBuffers();

    WPEView* m_view;
    WebKitWebView* m_webView = nullptr;
    WPEBuffer* m_pending = nullptr; // from WebKit, not drawn yet
    WPEBuffer* m_drawn = nullptr; // painted, waiting for Qt to show it
    WPEBuffer* m_shown = nullptr;
    GLuint m_texture = 0;
    bool m_swapRedBlue = false;
    // frames handed to the compositor, not drawn here, where it takes them
    std::unique_ptr<Subsurface> m_subsurface;
    bool m_onSubsurface = false;
    QOpenGLShaderProgram m_program;
    QPointF m_lastPointer;
    bool m_loadFailed = false;
    // The error page's load, which is not one of the application's
    bool m_errorPageNext = false;
    bool m_loadingErrorPage = false;
    QRect m_inputCursorArea;
    QString m_surroundingText;
    int m_inputCursor = 0;
    int m_inputAnchor = 0;
};

} // namespace QtWpeWebKit
