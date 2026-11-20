// QWebEngineSettings over WebKitSettings; a page's settings fall back to its profile's, and follow their changes
#pragma once

#include <QHash>
#include <QList>
#include <QString>

typedef struct _WebKitSettings WebKitSettings;

class QWebEngineSettings {
public:
    enum FontFamily { StandardFont, FixedFont, SerifFont, SansSerifFont, CursiveFont, FantasyFont, PictographFont };
    enum WebAttribute {
        AutoLoadImages,
        JavascriptEnabled,
        JavascriptCanOpenWindows,
        JavascriptCanAccessClipboard,
        LinksIncludedInFocusChain,
        LocalStorageEnabled,
        LocalContentCanAccessRemoteUrls,
        XSSAuditingEnabled,
        SpatialNavigationEnabled,
        LocalContentCanAccessFileUrls,
        HyperlinkAuditingEnabled,
        ScrollAnimatorEnabled,
        ErrorPageEnabled,
        PluginsEnabled,
        FullScreenSupportEnabled,
        ScreenCaptureEnabled,
        WebGLEnabled,
        Accelerated2dCanvasEnabled,
        AutoLoadIconsForPage,
        TouchIconsEnabled,
        FocusOnNavigationEnabled,
        PrintElementBackgrounds,
        AllowRunningInsecureContent,
        AllowGeolocationOnInsecureOrigins,
        AllowWindowActivationFromJavaScript,
        ShowScrollBars,
        PlaybackRequiresUserGesture,
        WebRTCPublicInterfacesOnly,
        JavascriptCanPaste,
        DnsPrefetchEnabled,
        PdfViewerEnabled,
        NavigateOnDropEnabled,
        ReadingFromCanvasEnabled,
        ForceDarkMode,
    };
    enum FontSize { MinimumFontSize, MinimumLogicalFontSize, DefaultFontSize, DefaultFixedFontSize };
    enum UnknownUrlSchemePolicy { InheritedUnknownUrlSchemePolicy, DisallowUnknownUrlSchemes, AllowUnknownUrlSchemesFromUserInteraction, AllowAllUnknownUrlSchemes };

    explicit QWebEngineSettings(QWebEngineSettings* parent = nullptr);
    ~QWebEngineSettings();
    QWebEngineSettings(const QWebEngineSettings&) = delete;
    QWebEngineSettings& operator=(const QWebEngineSettings&) = delete;

    void setFontFamily(FontFamily which, const QString& family);
    QString fontFamily(FontFamily which) const;
    void resetFontFamily(FontFamily which);
    void setFontSize(FontSize type, int size);
    int fontSize(FontSize type) const;
    void resetFontSize(FontSize type);
    void setAttribute(WebAttribute attribute, bool on);
    bool testAttribute(WebAttribute attribute) const;
    void resetAttribute(WebAttribute attribute);
    void setDefaultTextEncoding(const QString& encoding);
    QString defaultTextEncoding() const;
    UnknownUrlSchemePolicy unknownUrlSchemePolicy() const { return m_unknownUrlSchemePolicy; }
    void setUnknownUrlSchemePolicy(UnknownUrlSchemePolicy policy) { m_unknownUrlSchemePolicy = policy; }
    void resetUnknownUrlSchemePolicy() { m_unknownUrlSchemePolicy = InheritedUnknownUrlSchemePolicy; }

    WebKitSettings* webKitSettings() const { return m_webKitSettings; }

private:
    friend class QWebEngineProfile;
    void apply();
    // The profile's, which its pages take too
    void setUserAgent(const QString& userAgent);

    QWebEngineSettings* m_parent;
    QList<QWebEngineSettings*> m_children;
    WebKitSettings* m_webKitSettings;
    QHash<WebAttribute, bool> m_attributes;
    QHash<FontFamily, QString> m_fontFamilies;
    QHash<FontSize, int> m_fontSizes;
    QString m_defaultTextEncoding;
    UnknownUrlSchemePolicy m_unknownUrlSchemePolicy = InheritedUnknownUrlSchemePolicy;
};
