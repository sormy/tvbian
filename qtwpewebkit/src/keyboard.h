// WPE's key codes for Qt's key events, including those made without native codes: QTest, input methods,
// remote controls mapped by Qt
#pragma once

#include <glib.h>

class QKeyEvent;

namespace QtWpeWebKit {

// The XKB keysym
guint keyvalOf(const QKeyEvent* event);
// The hardware keycode, XKB's (evdev + 8)
guint keycodeOf(const QKeyEvent* event, guint keyval);

} // namespace QtWpeWebKit
