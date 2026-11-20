// WPEPlatform for Qt Widgets: one display per application, a toplevel and a view per web view
#pragma once

#include <QString>
#include <functional>
#include <wpe/wpe-platform.h>

namespace QtWpeWebKit {
class WebWidget;
}

G_BEGIN_DECLS
#define QTWPEWEBKIT_TYPE_DISPLAY (qtwpewebkit_display_get_type())
G_DECLARE_FINAL_TYPE(QtWpeWebKitDisplay, qtwpewebkit_display, QTWPEWEBKIT, DISPLAY, WPEDisplay)
#define QTWPEWEBKIT_TYPE_TOPLEVEL (qtwpewebkit_toplevel_get_type())
G_DECLARE_FINAL_TYPE(QtWpeWebKitToplevel, qtwpewebkit_toplevel, QTWPEWEBKIT, TOPLEVEL, WPEToplevel)
#define QTWPEWEBKIT_TYPE_VIEW (qtwpewebkit_view_get_type())
G_DECLARE_FINAL_TYPE(QtWpeWebKitView, qtwpewebkit_view, QTWPEWEBKIT, VIEW, WPEView)
#define QTWPEWEBKIT_TYPE_INPUT_METHOD_CONTEXT (qtwpewebkit_input_method_context_get_type())
G_DECLARE_FINAL_TYPE(QtWpeWebKitInputMethodContext, qtwpewebkit_input_method_context, QTWPEWEBKIT, INPUT_METHOD_CONTEXT, WPEInputMethodContext)
G_END_DECLS

namespace QtWpeWebKit {

// The application's display, connected on first use; needs Qt::AA_ShareOpenGLContexts
WPEDisplay* display();

void setViewWidget(WPEView* view, WebWidget* widget);

// The next view WebKit makes, handed to adopt: its inspector's, asked for just before
void adoptNextView(std::function<void(WPEView*)> adopt);

// WebKit follows a failed load with a load of its error page, unless the load was cancelled or went elsewhere
bool showsErrorPage(const GError* error);

// Text from Qt's input method for the page's focused field
void commitText(WPEView* view, const QString& text);
// Characters around the cursor, as an input method replaces a word
void deleteSurroundingText(WPEView* view, int offset, int length);
void setPreeditText(WPEView* view, const QString& text, int cursor);
// What the page's focused field takes, for on-screen keyboards
Qt::InputMethodHints inputHintsOf(WPEView* view);

} // namespace QtWpeWebKit
