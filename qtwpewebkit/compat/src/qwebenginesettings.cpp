#include "qwebenginesettings.h"

#include <QSet>
#include <wpe/webkit.h>

using Settings = QWebEngineSettings;

namespace {

using FlagSetter = void (*)(WebKitSettings*, gboolean);
using FontGetter = const gchar* (*)(WebKitSettings*);
using FontSetter = void (*)(WebKitSettings*, const gchar*);
using SizeGetter = guint32 (*)(WebKitSettings*);
using SizeSetter = void (*)(WebKitSettings*, guint32);

const QHash<Settings::WebAttribute, FlagSetter> flagSetters {
    { Settings::AutoLoadImages, webkit_settings_set_auto_load_images },
    { Settings::JavascriptEnabled, webkit_settings_set_enable_javascript },
    { Settings::JavascriptCanOpenWindows, webkit_settings_set_javascript_can_open_windows_automatically },
    { Settings::JavascriptCanAccessClipboard, webkit_settings_set_javascript_can_access_clipboard },
    { Settings::LinksIncludedInFocusChain, webkit_settings_set_enable_tabs_to_links },
    { Settings::LocalContentCanAccessRemoteUrls, webkit_settings_set_allow_universal_access_from_file_urls },
    { Settings::SpatialNavigationEnabled, webkit_settings_set_enable_spatial_navigation },
    { Settings::LocalContentCanAccessFileUrls, webkit_settings_set_allow_file_access_from_file_urls },
    { Settings::ScrollAnimatorEnabled, webkit_settings_set_enable_smooth_scrolling },
    { Settings::FullScreenSupportEnabled, webkit_settings_set_enable_fullscreen },
    { Settings::WebGLEnabled, webkit_settings_set_enable_webgl },
    { Settings::PrintElementBackgrounds, webkit_settings_set_print_backgrounds },
    { Settings::PlaybackRequiresUserGesture, webkit_settings_set_media_playback_requires_user_gesture },
};

// QtWebEngine's defaults that are off; every other attribute starts on
const QSet<Settings::WebAttribute> attributesOffByDefault {
    Settings::JavascriptCanAccessClipboard, Settings::LocalContentCanAccessRemoteUrls,
    Settings::XSSAuditingEnabled, Settings::SpatialNavigationEnabled, Settings::HyperlinkAuditingEnabled,
    Settings::ScrollAnimatorEnabled, Settings::PluginsEnabled, Settings::FullScreenSupportEnabled,
    Settings::ScreenCaptureEnabled, Settings::TouchIconsEnabled, Settings::FocusOnNavigationEnabled,
    Settings::AllowRunningInsecureContent, Settings::AllowGeolocationOnInsecureOrigins,
    Settings::AllowWindowActivationFromJavaScript, Settings::WebRTCPublicInterfacesOnly,
    Settings::JavascriptCanPaste, Settings::DnsPrefetchEnabled, Settings::ForceDarkMode,
    Settings::PlaybackRequiresUserGesture,
};

const QHash<Settings::FontFamily, std::pair<FontGetter, FontSetter>> fontAccessors {
    { Settings::StandardFont, { webkit_settings_get_default_font_family, webkit_settings_set_default_font_family } },
    { Settings::FixedFont, { webkit_settings_get_monospace_font_family, webkit_settings_set_monospace_font_family } },
    { Settings::SerifFont, { webkit_settings_get_serif_font_family, webkit_settings_set_serif_font_family } },
    { Settings::SansSerifFont, { webkit_settings_get_sans_serif_font_family, webkit_settings_set_sans_serif_font_family } },
    { Settings::CursiveFont, { webkit_settings_get_cursive_font_family, webkit_settings_set_cursive_font_family } },
    { Settings::FantasyFont, { webkit_settings_get_fantasy_font_family, webkit_settings_set_fantasy_font_family } },
    { Settings::PictographFont, { webkit_settings_get_pictograph_font_family, webkit_settings_set_pictograph_font_family } },
};

const QHash<Settings::FontSize, std::pair<SizeGetter, SizeSetter>> sizeAccessors {
    { Settings::MinimumFontSize, { webkit_settings_get_minimum_font_size, webkit_settings_set_minimum_font_size } },
    { Settings::DefaultFontSize, { webkit_settings_get_default_font_size, webkit_settings_set_default_font_size } },
    { Settings::DefaultFixedFontSize, { webkit_settings_get_default_monospace_font_size, webkit_settings_set_default_monospace_font_size } },
};

const int defaultMinimumLogicalFontSize = 6;

} // namespace

QWebEngineSettings::QWebEngineSettings(QWebEngineSettings* parent)
    : m_parent(parent)
    , m_webKitSettings(webkit_settings_new())
{
    if (m_parent)
        m_parent->m_children.append(this);
    // Chromium has them always, and QtWebEngine no setting for them; WebKit leaves them off
    webkit_settings_set_enable_webrtc(m_webKitSettings, TRUE);
    webkit_settings_set_enable_media_stream(m_webKitSettings, TRUE);
    apply();
}

QWebEngineSettings::~QWebEngineSettings()
{
    if (m_parent)
        m_parent->m_children.removeOne(this);
    g_object_unref(m_webKitSettings);
}

void QWebEngineSettings::setUserAgent(const QString& userAgent)
{
    webkit_settings_set_user_agent(m_webKitSettings, userAgent.toUtf8().constData());
    apply();
}

void QWebEngineSettings::apply()
{
    if (m_parent)
        webkit_settings_set_user_agent(m_webKitSettings, webkit_settings_get_user_agent(m_parent->m_webKitSettings));
    for (auto [attribute, set] : flagSetters.asKeyValueRange())
        set(m_webKitSettings, testAttribute(attribute));
    for (auto [family, accessors] : fontAccessors.asKeyValueRange()) {
        const QString name = fontFamily(family);
        if (!name.isEmpty())
            accessors.second(m_webKitSettings, name.toUtf8().constData());
    }
    for (auto [type, accessors] : sizeAccessors.asKeyValueRange())
        accessors.second(m_webKitSettings, fontSize(type));
    const QString encoding = defaultTextEncoding();
    if (!encoding.isEmpty())
        webkit_settings_set_default_charset(m_webKitSettings, encoding.toUtf8().constData());
    for (QWebEngineSettings* child : std::as_const(m_children))
        child->apply();
}

void QWebEngineSettings::setFontFamily(FontFamily which, const QString& family)
{
    m_fontFamilies.insert(which, family);
    apply();
}

QString QWebEngineSettings::fontFamily(FontFamily which) const
{
    if (m_fontFamilies.contains(which))
        return m_fontFamilies.value(which);
    if (m_parent)
        return m_parent->fontFamily(which);
    return QString::fromUtf8(fontAccessors.value(which).first(m_webKitSettings));
}

void QWebEngineSettings::resetFontFamily(FontFamily which)
{
    m_fontFamilies.remove(which);
    apply();
}

void QWebEngineSettings::setFontSize(FontSize type, int size)
{
    m_fontSizes.insert(type, size);
    apply();
}

int QWebEngineSettings::fontSize(FontSize type) const
{
    if (m_fontSizes.contains(type))
        return m_fontSizes.value(type);
    if (m_parent)
        return m_parent->fontSize(type);
    if (!sizeAccessors.contains(type))
        return defaultMinimumLogicalFontSize;
    return sizeAccessors.value(type).first(m_webKitSettings);
}

void QWebEngineSettings::resetFontSize(FontSize type)
{
    m_fontSizes.remove(type);
    apply();
}

void QWebEngineSettings::setAttribute(WebAttribute attribute, bool on)
{
    m_attributes.insert(attribute, on);
    apply();
}

bool QWebEngineSettings::testAttribute(WebAttribute attribute) const
{
    if (m_attributes.contains(attribute))
        return m_attributes.value(attribute);
    if (m_parent)
        return m_parent->testAttribute(attribute);
    return !attributesOffByDefault.contains(attribute);
}

void QWebEngineSettings::resetAttribute(WebAttribute attribute)
{
    m_attributes.remove(attribute);
    apply();
}

void QWebEngineSettings::setDefaultTextEncoding(const QString& encoding)
{
    m_defaultTextEncoding = encoding;
    apply();
}

QString QWebEngineSettings::defaultTextEncoding() const
{
    if (m_defaultTextEncoding.isEmpty() && m_parent)
        return m_parent->defaultTextEncoding();
    return m_defaultTextEncoding;
}
