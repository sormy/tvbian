#include "qwebengineview.h"

#include "webwidget.h"

#include <QContextMenuEvent>
#include <QCoreApplication>
#include <QKeyEvent>
#include <QVBoxLayout>
#include <wpe/webkit.h>

// WebKit's frames are shared with Qt's contexts; QtWebEngine sets this on load too
static void shareOpenGLContexts()
{
    QCoreApplication::setAttribute(Qt::AA_ShareOpenGLContexts);
}
Q_CONSTRUCTOR_FUNCTION(shareOpenGLContexts)

QWebEngineView::QWebEngineView(QWidget* parent)
    : QWidget(parent)
    , m_contextMenuRequest(new QWebEngineContextMenuRequest(this))
{
    auto* layout = new QVBoxLayout(this);
    layout->setContentsMargins({});
}

QWebEngineView::~QWebEngineView()
{
    delete m_webWidget;
    if (m_page)
        m_page->m_view = nullptr;
}

QWebEngineView* QWebEngineView::forPage(const QWebEnginePage* page)
{
    return page ? page->m_view.data() : nullptr;
}

QWebEnginePage* QWebEngineView::page() const
{
    if (!m_page) {
        auto* self = const_cast<QWebEngineView*>(this);
        self->setPage(new QWebEnginePage(self));
    }
    return m_page;
}

// The render widget is added only now, as QtWebEngine does: Falkon's WebView finds it as its new child
void QWebEngineView::setPage(QWebEnginePage* page)
{
    if (m_page == page)
        return;
    if (m_page) {
        disconnect(m_page, nullptr, this, nullptr);
        m_page->m_view = nullptr;
    }
    m_page = page;
    if (!page) {
        setWebWidget(nullptr);
        return;
    }
    m_page->m_view = this;
    if (page->m_inspectorView)
        showView(page->m_inspectorView);
    else
        setWebWidget(new QtWpeWebKit::WebWidget(page->webKitWebView(), this));
    // QtWebEngine hands the keys a page leaves to the view's parent; outside editable content, every key counts as left
    connect(m_webWidget, &QtWpeWebKit::WebWidget::keySent, this, [this](QKeyEvent* event) {
        if (!m_page->m_editing && parentWidget())
            QCoreApplication::sendEvent(parentWidget(), event);
    });

    connect(page, &QWebEnginePage::loadStarted, this, &QWebEngineView::loadStarted);
    connect(page, &QWebEnginePage::loadProgress, this, &QWebEngineView::loadProgress);
    connect(page, &QWebEnginePage::loadFinished, this, &QWebEngineView::loadFinished);
    connect(page, &QWebEnginePage::titleChanged, this, &QWebEngineView::titleChanged);
    connect(page, &QWebEnginePage::selectionChanged, this, &QWebEngineView::selectionChanged);
    connect(page, &QWebEnginePage::urlChanged, this, &QWebEngineView::urlChanged);
    connect(page, &QWebEnginePage::iconUrlChanged, this, &QWebEngineView::iconUrlChanged);
    connect(page, &QWebEnginePage::iconChanged, this, &QWebEngineView::iconChanged);
    connect(page, &QWebEnginePage::renderProcessTerminated, this, &QWebEngineView::renderProcessTerminated);
    connect(page, &QWebEnginePage::printRequested, this, &QWebEngineView::printRequested);
}

void QWebEngineView::setWebWidget(QtWpeWebKit::WebWidget* widget)
{
    delete m_webWidget;
    m_webWidget = widget;
    if (m_webWidget)
        layout()->addWidget(m_webWidget);
    setFocusProxy(m_webWidget);
}

void QWebEngineView::showView(WPEView* view)
{
    setWebWidget(new QtWpeWebKit::WebWidget(view, this));
    m_webWidget->show();
}

void QWebEngineView::requestContextMenu(WebKitContextMenu* menu, WebKitHitTestResult* hit)
{
    QWebEngineContextMenuRequest& request = *m_contextMenuRequest;
    int x = 0;
    int y = 0;
    webkit_context_menu_get_position(menu, &x, &y);
    request.m_position = QPoint(x, y);
    request.m_selectedText = webkit_hit_test_result_context_is_selection(hit) ? page()->selectedText() : QString();
    request.m_linkText = QString::fromUtf8(webkit_hit_test_result_get_link_label(hit));
    request.m_linkUrl = QUrl::fromEncoded(webkit_hit_test_result_get_link_uri(hit));
    const bool image = webkit_hit_test_result_context_is_image(hit);
    // WebKit does not tell video from audio
    request.m_mediaType = image ? QWebEngineContextMenuRequest::MediaTypeImage
        : webkit_hit_test_result_context_is_media(hit) ? QWebEngineContextMenuRequest::MediaTypeVideo
                                                         : QWebEngineContextMenuRequest::MediaTypeNone;
    request.m_mediaUrl = QUrl::fromEncoded(image ? webkit_hit_test_result_get_image_uri(hit) : webkit_hit_test_result_get_media_uri(hit));
    request.m_contentEditable = webkit_hit_test_result_context_is_editable(hit);
    // WebKit offers its guesses for a misspelled word, or says it has none
    QList<QPair<QString, GAction*>> guesses;
    bool misspelled = false;
    for (GList* item = webkit_context_menu_get_items(menu); item; item = item->next) {
        auto* menuItem = WEBKIT_CONTEXT_MENU_ITEM(item->data);
        const WebKitContextMenuAction action = webkit_context_menu_item_get_stock_action(menuItem);
        if (action == WEBKIT_CONTEXT_MENU_ACTION_SPELLING_GUESS)
            guesses.append({ QString::fromUtf8(webkit_context_menu_item_get_title(menuItem)),
                G_ACTION(g_object_ref(webkit_context_menu_item_get_gaction(menuItem))) });
        misspelled |= action == WEBKIT_CONTEXT_MENU_ACTION_SPELLING_GUESS || action == WEBKIT_CONTEXT_MENU_ACTION_NO_GUESSES_FOUND;
    }
    request.m_spellCheckerSuggestions.clear();
    for (const auto& guess : std::as_const(guesses))
        request.m_spellCheckerSuggestions.append(guess.first);
    request.m_misspelledWord.clear();
    page()->setSpellingGuesses(std::move(guesses));
    request.m_accepted = false;
    if (!misspelled) {
        showContextMenu();
        return;
    }
    // Chromium selects a misspelled word a click lands on, and its menu names it; WebKit only offers the guesses
    page()->selectWordAt(request.m_position, [view = QPointer<QWebEngineView>(this)](const QString& word) {
        if (!view)
            return;
        view->m_contextMenuRequest->m_misspelledWord = word;
        view->showContextMenu();
    });
}

void QWebEngineView::showContextMenu()
{
    const QPoint position = m_contextMenuRequest->m_position;
    QContextMenuEvent event(QContextMenuEvent::Mouse, position, mapToGlobal(position));
    QCoreApplication::sendEvent(this, &event);
}
