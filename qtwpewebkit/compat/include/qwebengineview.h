// A widget showing a QWebEnginePage: its single child, a QtWpeWebKit::WebWidget, draws the page and takes input
#pragma once

#include "qwebenginecontextmenurequest.h"
#include "qwebenginepage.h"

#include <QPointer>
#include <QWidget>

class QMenu;
typedef struct _WebKitContextMenu WebKitContextMenu;
typedef struct _WebKitHitTestResult WebKitHitTestResult;
class QPrinter;
namespace QtWpeWebKit {
class WebWidget;
}

class QWebEngineView : public QWidget {
    Q_OBJECT
public:
    explicit QWebEngineView(QWidget* parent = nullptr);
    ~QWebEngineView() override;

    static QWebEngineView* forPage(const QWebEnginePage* page);

    QWebEnginePage* page() const;
    void setPage(QWebEnginePage* page);

    void load(const QUrl& url) { page()->load(url); }
    void load(const QWebEngineHttpRequest& request) { page()->load(request); }
    void setHtml(const QString& html, const QUrl& baseUrl = {}) { page()->setHtml(html, baseUrl); }
    void setContent(const QByteArray& data, const QString& mimeType = {}, const QUrl& baseUrl = {}) { page()->setContent(data, mimeType, baseUrl); }
    QWebEngineHistory* history() const { return page()->history(); }
    QString title() const { return page()->title(); }
    void setUrl(const QUrl& url) { page()->setUrl(url); }
    QUrl url() const { return page()->url(); }
    QUrl iconUrl() const { return page()->iconUrl(); }
    QIcon icon() const { return page()->icon(); }
    bool hasSelection() const { return page()->hasSelection(); }
    QString selectedText() const { return page()->selectedText(); }
    QAction* pageAction(QWebEnginePage::WebAction action) const { return page()->action(action); }
    void triggerPageAction(QWebEnginePage::WebAction action, bool checked = false) { page()->triggerAction(action, checked); }
    qreal zoomFactor() const { return page()->zoomFactor(); }
    void setZoomFactor(qreal factor) { page()->setZoomFactor(factor); }
    void findText(const QString& subString, QWebEnginePage::FindFlags options = {},
        const std::function<void(const QWebEngineFindTextResult&)>& resultCallback = {})
    {
        page()->findText(subString, options, resultCallback);
    }
    QWebEngineSettings* settings() const { return page()->settings(); }
    QSize sizeHint() const override { return { 800, 600 }; }
    QWebEngineContextMenuRequest* lastContextMenuRequest() const { return m_contextMenuRequest; }
    QMenu* createStandardContextMenu() { return nullptr; }
    void printToPdf(const QString&, const QPageLayout& = QPageLayout(QPageSize(QPageSize::A4), QPageLayout::Portrait, QMarginsF()),
        const QPageRanges& = {}) { }
    // Printing has no WPE counterpart
    void print(QPrinter*) { QMetaObject::invokeMethod(this, &QWebEngineView::printFinished, Qt::QueuedConnection, false); }

public Q_SLOTS:
    void stop() { triggerPageAction(QWebEnginePage::Stop); }
    void back() { triggerPageAction(QWebEnginePage::Back); }
    void forward() { triggerPageAction(QWebEnginePage::Forward); }
    void reload() { triggerPageAction(QWebEnginePage::Reload); }

Q_SIGNALS:
    void loadStarted();
    void loadProgress(int progress);
    void loadFinished(bool ok);
    void titleChanged(const QString& title);
    void selectionChanged();
    void urlChanged(const QUrl& url);
    void iconUrlChanged(const QUrl& url);
    void iconChanged(const QIcon& icon);
    void renderProcessTerminated(QWebEnginePage::RenderProcessTerminationStatus terminationStatus, int exitCode);
    void pdfPrintingFinished(const QString& filePath, bool success);
    void printRequested();
    void printFinished(bool success);

protected:
    virtual QWebEngineView* createWindow(QWebEnginePage::WebWindowType) { return nullptr; }

private:
    friend class QWebEnginePage;
    // Shows the menu the page asked for, as QtWebEngine does: through contextMenuEvent()
    void requestContextMenu(WebKitContextMenu* menu, WebKitHitTestResult* hit);
    void showContextMenu();
    // A view WebKit made, as its inspector's, in place of the page's
    void showView(WPEView* view);
    void setWebWidget(QtWpeWebKit::WebWidget* widget);

    QPointer<QWebEnginePage> m_page;
    QtWpeWebKit::WebWidget* m_webWidget = nullptr;
    QWebEngineContextMenuRequest* m_contextMenuRequest;
};
