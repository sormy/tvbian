#include "keyboard.h"

#include "platform.h"

#include <QHash>
#include <QKeyEvent>

namespace QtWpeWebKit {

// Keys whose text, if any, is a control character
static const QHash<int, guint> keyvalsByQtKey {
    { Qt::Key_Escape, WPE_KEY_Escape }, { Qt::Key_Tab, WPE_KEY_Tab }, { Qt::Key_Backtab, WPE_KEY_ISO_Left_Tab },
    { Qt::Key_Backspace, WPE_KEY_BackSpace }, { Qt::Key_Return, WPE_KEY_Return }, { Qt::Key_Enter, WPE_KEY_KP_Enter },
    { Qt::Key_Insert, WPE_KEY_Insert }, { Qt::Key_Delete, WPE_KEY_Delete }, { Qt::Key_Pause, WPE_KEY_Pause },
    { Qt::Key_Print, WPE_KEY_Print }, { Qt::Key_Home, WPE_KEY_Home }, { Qt::Key_End, WPE_KEY_End },
    { Qt::Key_Left, WPE_KEY_Left }, { Qt::Key_Up, WPE_KEY_Up }, { Qt::Key_Right, WPE_KEY_Right },
    { Qt::Key_Down, WPE_KEY_Down }, { Qt::Key_PageUp, WPE_KEY_Page_Up }, { Qt::Key_PageDown, WPE_KEY_Page_Down },
    { Qt::Key_Shift, WPE_KEY_Shift_L }, { Qt::Key_Control, WPE_KEY_Control_L }, { Qt::Key_Meta, WPE_KEY_Super_L },
    { Qt::Key_Alt, WPE_KEY_Alt_L }, { Qt::Key_CapsLock, WPE_KEY_Caps_Lock }, { Qt::Key_NumLock, WPE_KEY_Num_Lock },
    { Qt::Key_ScrollLock, WPE_KEY_Scroll_Lock }, { Qt::Key_Menu, WPE_KEY_Menu }, { Qt::Key_Select, WPE_KEY_Select },
    { Qt::Key_Cancel, WPE_KEY_Cancel }, { Qt::Key_Back, WPE_KEY_Back }, { Qt::Key_Forward, WPE_KEY_Forward },
    { Qt::Key_Refresh, WPE_KEY_Refresh }, { Qt::Key_Reload, WPE_KEY_Reload }, { Qt::Key_Stop, WPE_KEY_Stop },
    { Qt::Key_HomePage, WPE_KEY_HomePage }, { Qt::Key_Search, WPE_KEY_Search }, { Qt::Key_Favorites, WPE_KEY_Favorites },
    { Qt::Key_VolumeDown, WPE_KEY_AudioLowerVolume }, { Qt::Key_VolumeMute, WPE_KEY_AudioMute },
    { Qt::Key_VolumeUp, WPE_KEY_AudioRaiseVolume }, { Qt::Key_MediaPlay, WPE_KEY_AudioPlay },
    { Qt::Key_MediaTogglePlayPause, WPE_KEY_AudioPlay }, { Qt::Key_MediaPause, WPE_KEY_AudioPause },
    { Qt::Key_MediaStop, WPE_KEY_AudioStop }, { Qt::Key_MediaPrevious, WPE_KEY_AudioPrev },
    { Qt::Key_MediaNext, WPE_KEY_AudioNext }, { Qt::Key_MediaRecord, WPE_KEY_AudioRecord },
    { Qt::Key_AudioRewind, WPE_KEY_AudioRewind }, { Qt::Key_AudioForward, WPE_KEY_AudioForward },
    { Qt::Key_Red, WPE_KEY_Red }, { Qt::Key_Green, WPE_KEY_Green }, { Qt::Key_Yellow, WPE_KEY_Yellow },
    { Qt::Key_Blue, WPE_KEY_Blue },
};

guint keyvalOf(const QKeyEvent* event)
{
    if (event->nativeVirtualKey())
        return event->nativeVirtualKey();
    const int key = event->key();
    if (key >= Qt::Key_F1 && key <= Qt::Key_F35)
        return WPE_KEY_F1 + (key - Qt::Key_F1);
    if (const guint keyval = keyvalsByQtKey.value(key))
        return keyval;
    const QList<uint> text = event->text().toUcs4();
    if (!text.isEmpty() && QChar::isPrint(text.first()))
        return wpe_unicode_to_keyval(text.first());
    // With Control the text is a control character: the key names the letter, Qt's in upper case
    if (key >= Qt::Key_Space && key <= Qt::Key_ydiaeresis) {
        const QChar letter(key);
        return wpe_unicode_to_keyval((event->modifiers() & Qt::ShiftModifier ? letter : letter.toLower()).unicode());
    }
    return 0;
}

// The first key that types the keysym in the display's keymap
guint keycodeOf(const QKeyEvent* event, guint keyval)
{
    if (event->nativeScanCode() || !keyval)
        return event->nativeScanCode();
    WPEKeymapEntry* entries = nullptr;
    guint count = 0;
    if (!wpe_keymap_get_entries_for_keyval(wpe_display_get_keymap(display()), keyval, &entries, &count))
        return 0;
    const guint keycode = count ? entries[0].keycode : 0;
    g_free(entries);
    return keycode;
}

} // namespace QtWpeWebKit
