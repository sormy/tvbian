// A context menu's data, taken from WebKit's hit test and menu when the page asks for one
#pragma once

#include <QObject>
#include <QPoint>
#include <QStringList>
#include <QUrl>

class QWebEngineContextMenuRequest : public QObject {
    Q_OBJECT
public:
    enum MediaType { MediaTypeNone, MediaTypeImage, MediaTypeVideo, MediaTypeAudio, MediaTypeCanvas, MediaTypeFile, MediaTypePlugin };
    enum MediaFlag { MediaInError = 0x1, MediaPaused = 0x2, MediaMuted = 0x4, MediaLoop = 0x8, MediaCanSave = 0x10, MediaHasAudio = 0x20 };
    Q_DECLARE_FLAGS(MediaFlags, MediaFlag)
    enum EditFlag { CanUndo = 0x1, CanRedo = 0x2, CanCut = 0x4, CanCopy = 0x8, CanPaste = 0x10, CanDelete = 0x20, CanSelectAll = 0x40 };
    Q_DECLARE_FLAGS(EditFlags, EditFlag)

    using QObject::QObject;
    QPoint position() const { return m_position; }
    QString selectedText() const { return m_selectedText; }
    QString linkText() const { return m_linkText; }
    QUrl linkUrl() const { return m_linkUrl; }
    QUrl mediaUrl() const { return m_mediaUrl; }
    MediaType mediaType() const { return m_mediaType; }
    bool isContentEditable() const { return m_contentEditable; }
    QString misspelledWord() const { return m_misspelledWord; }
    QStringList spellCheckerSuggestions() const { return m_spellCheckerSuggestions; }
    bool isAccepted() const { return m_accepted; }
    void setAccepted(bool accepted) { m_accepted = accepted; }
    MediaFlags mediaFlags() const { return {}; }
    EditFlags editFlags() const { return {}; }

private:
    friend class QWebEngineView;
    // Off the page until the page asks for a menu
    QPoint m_position { -1, -1 };
    QString m_selectedText;
    QString m_linkText;
    QUrl m_linkUrl;
    QUrl m_mediaUrl;
    MediaType m_mediaType = MediaTypeNone;
    bool m_contentEditable = false;
    QString m_misspelledWord;
    QStringList m_spellCheckerSuggestions;
    bool m_accepted = false;
};
