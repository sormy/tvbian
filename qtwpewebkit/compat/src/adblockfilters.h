// Adblock Plus filter lists as WebKit content blocker rules
#pragma once

#include <QByteArray>
#include <QString>

namespace QtWpeWebKit {

// The JSON rule list of what WebKit's content blockers can express of the filters; the rest is left out
QByteArray contentBlockerRules(const QString& filterLists);

} // namespace QtWpeWebKit
