// What a web process and the UI process say about a request: GVariants, each after its size as a native guint32;
// and the user message a page's console message goes to its view in
#pragma once

namespace QtWpeWebKit {

// Page id, URL, page URL, method, Sec-Fetch-Dest and Accept headers
inline constexpr char requestFormat[] = "(tsssss)";
// Blocked, redirect URL or empty, headers to set
inline constexpr char replyFormat[] = "(bsa{ss})";

inline constexpr char consoleMessageName[] = "qtwpewebkit-console";
// Level, text, source URL, line
inline constexpr char consoleMessageFormat[] = "(ussu)";
// QWebEnginePage::JavaScriptConsoleMessageLevel's values
enum ConsoleLevel : unsigned { ConsoleInfo, ConsoleWarning, ConsoleError };

} // namespace QtWpeWebKit
