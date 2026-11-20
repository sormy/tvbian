// A web page: one WebKitWebView, shown by at most one QWebEngineView
#pragma once

#include "qwebenginedownloadrequest.h"
#include "qwebenginerequests.h"
#include "qwebengineurlrequestinfo.h"

#include <QColor>
#include <QIcon>
#include <QObject>
#include <QPageLayout>
#include <QPageRanges>
#include <QPointer>
#include <QPointF>
#include <QSizeF>
#include <QUrl>
#include <QVariant>
#include <atomic>
#include <functional>
#include <optional>
#include <memory>

class QAction;
class QAuthenticator;
class QWebChannel;
class QWebEngineHistory;
class QWebEngineProfile;
class QWebEngineScriptCollection;
class QWebEngineSettings;
class QWebEngineView;
namespace QtWpeWebKit {
class RequestInterception;
class WebChannelTransport;
}
typedef struct _GAction GAction;
typedef struct _WebKitPermissionRequest WebKitPermissionRequest;
typedef struct _WebKitUserContentManager WebKitUserContentManager;
typedef struct _WebKitUserScript WebKitUserScript;
typedef struct _WebKitWebView WebKitWebView;
typedef struct _WPEView WPEView;

class QWebEnginePage : public QObject {
    Q_OBJECT
public:
    enum WebAction {
        NoWebAction = -1,
        Back,
        Forward,
        Stop,
        Reload,
        Cut,
        Copy,
        Paste,
        Undo,
        Redo,
        SelectAll,
        ReloadAndBypassCache,
        PasteAndMatchStyle,
        OpenLinkInThisWindow,
        OpenLinkInNewWindow,
        OpenLinkInNewTab,
        CopyLinkToClipboard,
        DownloadLinkToDisk,
        CopyImageToClipboard,
        CopyImageUrlToClipboard,
        DownloadImageToDisk,
        CopyMediaUrlToClipboard,
        ToggleMediaControls,
        ToggleMediaLoop,
        ToggleMediaPlayPause,
        ToggleMediaMute,
        DownloadMediaToDisk,
        InspectElement,
        ExitFullScreen,
        RequestClose,
        Unselect,
        SavePage,
        OpenLinkInNewBackgroundTab,
        ViewSource,
        ToggleBold,
        ToggleItalic,
        ToggleUnderline,
        ToggleStrikethrough,
        AlignLeft,
        AlignCenter,
        AlignRight,
        AlignJustified,
        Indent,
        Outdent,
        InsertOrderedList,
        InsertUnorderedList,
        ChangeTextDirectionLTR,
        ChangeTextDirectionRTL,
        WebActionCount
    };
    Q_ENUM(WebAction)
    enum FindFlag { FindBackward = 1, FindCaseSensitively = 2 };
    Q_DECLARE_FLAGS(FindFlags, FindFlag)
    enum WebWindowType { WebBrowserWindow, WebBrowserTab, WebDialog, WebBrowserBackgroundTab };
    enum PermissionPolicy { PermissionUnknown, PermissionGrantedByUser, PermissionDeniedByUser };
    enum NavigationType {
        NavigationTypeLinkClicked,
        NavigationTypeTyped,
        NavigationTypeFormSubmitted,
        NavigationTypeBackForward,
        NavigationTypeReload,
        NavigationTypeOther,
        NavigationTypeRedirect,
    };
    Q_ENUM(NavigationType)
    enum Feature {
        Notifications = 0,
        Geolocation = 1,
        MediaAudioCapture = 2,
        MediaVideoCapture,
        MediaAudioVideoCapture,
        MouseLock,
        DesktopVideoCapture,
        DesktopAudioVideoCapture,
        ClipboardReadWrite,
        LocalFontsAccess,
    };
    Q_ENUM(Feature)
    enum FileSelectionMode { FileSelectOpen, FileSelectOpenMultiple, FileSelectUploadFolder, FileSelectSave };
    enum JavaScriptConsoleMessageLevel { InfoMessageLevel = 0, WarningMessageLevel, ErrorMessageLevel };
    enum RenderProcessTerminationStatus { NormalTerminationStatus = 0, AbnormalTerminationStatus, CrashedTerminationStatus, KilledTerminationStatus };
    Q_ENUM(RenderProcessTerminationStatus)
    enum class LifecycleState { Active, Frozen, Discarded };

    explicit QWebEnginePage(QObject* parent = nullptr);
    explicit QWebEnginePage(QWebEngineProfile* profile, QObject* parent = nullptr);
    ~QWebEnginePage() override;

    QWebEngineHistory* history() const { return m_history.get(); }
    QWebEngineProfile* profile() const { return m_profile; }
    QWebEngineSettings* settings() const { return m_settings.get(); }

    bool hasSelection() const { return !m_selectedText.isEmpty(); }
    QString selectedText() const { return m_selectedText; }
    QAction* action(WebAction action) const;
    virtual void triggerAction(WebAction action, bool checked = false);
    void replaceMisspelledWord(const QString& replacement);
    void findText(const QString& subString, FindFlags options = {},
        const std::function<void(const QWebEngineFindTextResult&)>& resultCallback = {});

    void setFeaturePermission(const QUrl& securityOrigin, Feature feature, PermissionPolicy policy);
    bool isLoading() const;
    void load(const QUrl& url);
    void load(const QWebEngineHttpRequest& request) { load(request.url()); }
    // WebKit suggests the file name
    void download(const QUrl& url, const QString& = {});
    void setHtml(const QString& html, const QUrl& baseUrl = {});
    void setContent(const QByteArray& data, const QString& mimeType = {}, const QUrl& baseUrl = {});
    void toHtml(const std::function<void(const QString&)>& resultCallback) const;
    void toPlainText(const std::function<void(const QString&)>& resultCallback) const;
    QString title() const { return m_title; }
    void setUrl(const QUrl& url) { load(url); }
    QUrl url() const;
    QUrl requestedUrl() const { return m_requestedUrl; }
    QUrl iconUrl() const { return {}; }
    QIcon icon() const;
    qreal zoomFactor() const;
    void setZoomFactor(qreal factor);
    QPointF scrollPosition() const { return m_scrollPosition; }
    QSizeF contentsSize() const { return m_contentsSize; }

    void runJavaScript(const QString& scriptSource, const std::function<void(const QVariant&)>& resultCallback)
    {
        runJavaScript(scriptSource, 0, resultCallback);
    }
    void runJavaScript(const QString& scriptSource, quint32 worldId = 0,
        const std::function<void(const QVariant&)>& resultCallback = {});
    QWebChannel* webChannel() const { return m_webChannel; }
    void setWebChannel(QWebChannel* channel, quint32 worldId = 0);
    QColor backgroundColor() const { return m_backgroundColor; }
    void setBackgroundColor(const QColor& color);
    void save(const QString&, QWebEngineDownloadRequest::SavePageFormat = QWebEngineDownloadRequest::MimeHtmlSaveFormat) const { }
    bool isAudioMuted() const;
    void setAudioMuted(bool muted);
    bool recentlyAudible() const;
    qint64 renderProcessPid() const { return 0; }
    void printToPdf(const QString&, const QPageLayout& = QPageLayout(QPageSize(QPageSize::A4), QPageLayout::Portrait, QMarginsF()),
        const QPageRanges& = {}) { }
    void printToPdf(const std::function<void(const QByteArray&)>&,
        const QPageLayout& = QPageLayout(QPageSize(QPageSize::A4), QPageLayout::Portrait, QMarginsF()),
        const QPageRanges& = {}) { }
    // This page shows WebKit's inspector of page, in its own view
    void setInspectedPage(QWebEnginePage* page);
    QWebEnginePage* inspectedPage() const { return m_inspectedPage; }
    void setDevToolsPage(QWebEnginePage* devToolsPage);
    QWebEnginePage* devToolsPage() const { return m_devToolsPage; }
    // Called after the profile's
    void setUrlRequestInterceptor(QWebEngineUrlRequestInterceptor* interceptor) { m_requestInterceptor = interceptor; }
    QWebEngineUrlRequestInterceptor* urlRequestInterceptor() const { return m_requestInterceptor; }
    LifecycleState lifecycleState() const { return LifecycleState::Active; }
    void setLifecycleState(LifecycleState) { }
    bool isVisible() const { return true; }
    void setVisible(bool) { }

    WebKitWebView* webKitWebView() const { return m_webView; }

Q_SIGNALS:
    void loadStarted();
    void loadProgress(int progress);
    void loadFinished(bool ok);
    void linkHovered(const QString& url);
    void selectionChanged();
    void geometryChangeRequested(const QRect& geom);
    void windowCloseRequested();
    void featurePermissionRequested(const QUrl& securityOrigin, QWebEnginePage::Feature feature);
    void featurePermissionRequestCanceled(const QUrl& securityOrigin, QWebEnginePage::Feature feature);
    void fullScreenRequested(QWebEngineFullScreenRequest fullScreenRequest);
    void registerProtocolHandlerRequested(QWebEngineRegisterProtocolHandlerRequest request);
    void selectClientCertificate(QWebEngineClientCertificateSelection clientCertSelection);
    void authenticationRequired(const QUrl& requestUrl, QAuthenticator* authenticator);
    void proxyAuthenticationRequired(const QUrl& requestUrl, QAuthenticator* authenticator, const QString& proxyHost);
    void renderProcessTerminated(QWebEnginePage::RenderProcessTerminationStatus terminationStatus, int exitCode);
    void certificateError(const QWebEngineCertificateError& certificateError);
    void newWindowRequested(QWebEngineNewWindowRequest& request);
    void titleChanged(const QString& title);
    void urlChanged(const QUrl& url);
    void iconUrlChanged(const QUrl& url);
    void iconChanged(const QIcon& icon);
    void zoomFactorChanged(qreal factor);
    void scrollPositionChanged(const QPointF& position);
    void contentsSizeChanged(const QSizeF& size);
    void audioMutedChanged(bool muted);
    void recentlyAudibleChanged(bool recentlyAudible);
    void renderProcessPidChanged(qint64 pid);
    void pdfPrintingFinished(const QString& filePath, bool success);
    void printRequested();
    void visibleChanged(bool visible);
    void lifecycleStateChanged(QWebEnginePage::LifecycleState state);
    void findTextFinished(const QWebEngineFindTextResult& result);

protected:
    virtual QWebEnginePage* createWindow(WebWindowType) { return nullptr; }
    virtual QStringList chooseFiles(FileSelectionMode mode, const QStringList& oldFiles, const QStringList& acceptedMimeTypes);
    virtual void javaScriptAlert(const QUrl& securityOrigin, const QString& msg);
    virtual bool javaScriptConfirm(const QUrl& securityOrigin, const QString& msg);
    virtual bool javaScriptPrompt(const QUrl& securityOrigin, const QString& msg, const QString& defaultValue, QString* result);
    virtual void javaScriptConsoleMessage(JavaScriptConsoleMessageLevel level, const QString& message, int lineNumber,
        const QString& sourceID);
    virtual bool acceptNavigationRequest(const QUrl&, NavigationType, bool) { return true; }

private:
    friend class QWebEngineView;
    friend class QtWpeWebKit::RequestInterception;
    friend class QWebEngineUrlRequestJob;
    friend class QWebEngineNewWindowRequest;
    // WebKit's signal handlers
    struct WebViewSignals;
    friend struct WebViewSignals;
    // Permission, certificate and authentication requests
    struct RequestSignals;
    friend struct RequestSignals;
    void connectRequestSignals();
    void downloadAs(const QUrl& url);
    // From the page's own title, or its URL without one
    void updateTitle(const QString& pageTitle);
    void finishLoad();
    // A scheme handler redirects the page's own request: its load goes on at the new URL
    void redirectLoad(const QUrl& url);
    void emitLoadFinished();
    void denyPermissionRequests();

    QWebEngineProfile* m_profile;
    std::unique_ptr<QWebEngineSettings> m_settings;
    // The page's own, so script messages tell their page
    WebKitUserContentManager* m_userContentManager;
    // The page whose window.open made it, if any: its view is related to that one's
    WebKitWebView* m_openerView;
    WebKitWebView* m_webView;
    std::unique_ptr<QWebEngineHistory> m_history;
    QPointer<QWebEngineView> m_view;
    QPointer<QWebEnginePage> m_inspectedPage;
    QPointer<QWebEnginePage> m_devToolsPage;
    // WebKit's view of its inspector, which this page's view shows in place of the page
    WPEView* m_inspectorView = nullptr;
    QUrl m_requestedUrl;
    QColor m_backgroundColor = Qt::white;
    QWebChannel* m_webChannel = nullptr;
    std::unique_ptr<QtWpeWebKit::WebChannelTransport> m_webChannelTransport;
    mutable QHash<WebAction, QAction*> m_actions;
    QString m_findText;
    bool m_findCaseSensitive = false;
    // WebKit counts the matches but does not say which one is active
    enum class FindMove { First, Last, Next, Previous } m_findMove = FindMove::First;
    int m_findActiveMatch = 0;
    std::function<void(const QWebEngineFindTextResult&)> m_findCallback;
    // The last menu's spelling suggestions, each with the action WebKit replaces the word by
    QList<QPair<QString, GAction*>> m_spellingGuesses;
    void setSpellingGuesses(QList<QPair<QString, GAction*>> guesses);
    // Selects the word under a point of the view, for the word it gives
    void selectWordAt(QPoint position, const std::function<void(const QString&)>& selected);
    QString m_title;
    bool m_loadFailed = false;
    // By an interceptor; WebKit shows an empty page instead and reports no failure
    std::atomic<bool> m_mainFrameBlocked = false;
    // WebKit's error page, loaded after a failure
    bool m_errorPageNext = false;
    bool m_loadingErrorPage = false;
    quint64 m_loadCount = 0;
    // Finished, waiting for its title
    std::optional<bool> m_loadSucceeded;
    // By load(), setHtml() or setContent(), not by the page
    bool m_loadRequested = false;
    bool m_redirecting = false;
    // Of the latest navigation, for its frame's request
    NavigationType m_navigationType = NavigationTypeOther;
    QPointer<QWebEngineUrlRequestInterceptor> m_requestInterceptor;
    // Reported by the page's scripts, so known a little after the fact
    QString m_selectedText;
    QPointF m_scrollPosition;
    QSizeF m_contentsSize;
    bool m_editing = false;
    WebKitUserScript* m_stateScript;
    // Waiting for setFeaturePermission(); always the current page's origin
    QMultiHash<Feature, WebKitPermissionRequest*> m_permissionRequests;
};

Q_DECLARE_OPERATORS_FOR_FLAGS(QWebEnginePage::FindFlags)
