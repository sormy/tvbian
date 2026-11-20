// The view as a widget: what it draws, the input it gives the page, focus, size, visibility and cursor
#include "webtest.h"

#include <QSet>

#include <QApplication>
#include <QInputMethodEvent>
#include <QLineEdit>
#include <QScreen>
#include <QWebEngineContextMenuRequest>
#include <QWebEngineProfile>

static const QString pageHtml = QStringLiteral(R"(<html><head><title>widget</title><style>
html, body { margin: 0; height: 3000px; background: rgb(0, 128, 255); }
div { position: absolute; width: 100px; height: 100px; }
</style></head><body>
<div id=red style="left: 50px; top: 50px; background: rgb(255, 0, 0); cursor: default"></div>
<div style="left: 200px; top: 0; cursor: pointer"></div>
<div style="left: 200px; top: 100px; cursor: text"></div>
<div style="left: 300px; top: 0; cursor: crosshair"></div>
<input id=input style="position: absolute; left: 0; top: 220px">
<script>
window.events = [];
const modifiers = e => (e.shiftKey ? 'S' : '') + (e.ctrlKey ? 'C' : '') + (e.altKey ? 'A' : '');
for (const type of ['mousedown', 'mouseup', 'click', 'dblclick', 'auxclick', 'contextmenu'])
    addEventListener(type, e => {
        events.push([type, e.button, e.buttons, e.clientX + ',' + e.clientY, modifiers(e)].join(' '));
        if (type === 'contextmenu')
            e.preventDefault();
    });
addEventListener('mousemove', e => window.lastMove = e.clientX + ',' + e.clientY);
addEventListener('wheel', e => events.push(['wheel', Math.sign(e.deltaX), Math.sign(e.deltaY), e.clientX + ',' + e.clientY].join(' ')));
addEventListener('keydown', e => events.push(['keydown', e.key, modifiers(e)].join(' ')));
addEventListener('focus', () => events.push('focus'));
addEventListener('blur', () => events.push('blur'));
</script></body></html>)");

static QStringList events(QWebEnginePage* page)
{
    return evaluate(page, QStringLiteral("events")).toStringList();
}

static bool isNear(QColor actual, QColor expected)
{
    const int tolerance = 8;
    return qAbs(actual.red() - expected.red()) <= tolerance && qAbs(actual.green() - expected.green()) <= tolerance
        && qAbs(actual.blue() - expected.blue()) <= tolerance;
}

// Real input comes with increasing timestamps; WebKit drops a move as old as the one before
static void sendInput(QWidget* target, QInputEvent&& event)
{
    static ulong timestamp = 0;
    timestamp += 20;
    event.setTimestamp(timestamp);
    QApplication::sendEvent(target, &event);
}

struct Key {
    int qtKey;
    QString text;
    quint32 scanCode; // evdev + 8, as Wayland gives it
    quint32 keysym;
};
Q_DECLARE_METATYPE(Key)

// Time the spellchecker takes to mark typed words
static const int spellcheckMs = 1500;

// A view that takes its context menus itself, so the menu's request can be read and no menu opens
struct MenuView : QWebEngineView {
    bool menuSeen = false;
    void contextMenuEvent(QContextMenuEvent*) override { menuSeen = true; }
};

class tst_Widget : public QObject {
    Q_OBJECT

private Q_SLOTS:
    void init()
    {
        m_window = std::make_unique<QWidget>();
        m_view = new QWebEngineView(m_window.get());
        m_view->setGeometry(0, 0, 400, 300);
        m_other = new QLineEdit(m_window.get());
        m_other->setGeometry(0, 310, 200, 30);
        m_window->resize(420, 360);
        m_window->show();
        QVERIFY(QTest::qWaitForWindowExposed(m_window.get()));
        m_window->activateWindow();
        if (!QTest::qWaitForWindowActive(m_window.get()))
            qWarning("Window not active");
        QVERIFY(setsHtml(m_view->page(), pageHtml));
        m_view->setFocus();
    }

    void cleanup() { m_window.reset(); }

    void renders()
    {
        auto pixelAt = [this](QPoint point) {
            const QImage image = m_view->grab().toImage();
            return image.pixelColor(point * image.devicePixelRatio());
        };
        QTRY_VERIFY2(isNear(pixelAt({ 10, 10 }), QColor(0, 128, 255)), qPrintable(pixelAt({ 10, 10 }).name()));
        QVERIFY2(isNear(pixelAt({ 100, 100 }), QColor(255, 0, 0)), qPrintable(pixelAt({ 100, 100 }).name()));
        QVERIFY2(isNear(pixelAt({ 160, 100 }), QColor(0, 128, 255)), qPrintable(pixelAt({ 160, 100 }).name()));
    }

    // Developer tools in a view of their own, as Falkon shows them under the page
    void devTools()
    {
        QWidget toolsWindow;
        toolsWindow.resize(640, 400);
        auto* tools = new QWebEngineView(&toolsWindow);
        tools->setGeometry(0, 0, 640, 400);
        // as Falkon does: the inspected page set while its view is still hidden
        tools->page()->setInspectedPage(m_view->page());
        toolsWindow.show();
        QVERIFY(QTest::qWaitForWindowExposed(&toolsWindow));
        QCOMPARE(tools->page()->inspectedPage(), m_view->page());
        QCOMPARE(m_view->page()->devToolsPage(), tools->page());
        // the inspector's own interface, not an empty view: many colours
        auto colours = [tools] {
            const QImage image = tools->grab().toImage();
            QSet<QRgb> seen;
            for (int y = 0; y < image.height(); y += 7)
                for (int x = 0; x < image.width(); x += 7)
                    seen.insert(image.pixel(x, y));
            return seen.size();
        };
        QTRY_VERIFY_WITH_TIMEOUT(colours() > 8, 20000);
        tools->page()->setInspectedPage(nullptr);
        QCOMPARE(m_view->page()->devToolsPage(), nullptr);
    }

    void mouseButtons_data()
    {
        QTest::addColumn<int>("button");
        QTest::addColumn<int>("modifiers");
        QTest::addColumn<QStringList>("expected");
        QTest::newRow("left") << int(Qt::LeftButton) << int(Qt::NoModifier)
                              << QStringList { "mousedown 0 1 30,40 ", "mouseup 0 0 30,40 ", "click 0 0 30,40 " };
        QTest::newRow("shift+ctrl left") << int(Qt::LeftButton) << int(Qt::ShiftModifier | Qt::ControlModifier)
                                         << QStringList { "mousedown 0 1 30,40 SC", "mouseup 0 0 30,40 SC" };
        QTest::newRow("middle") << int(Qt::MiddleButton) << int(Qt::NoModifier)
                                << QStringList { "mousedown 1 4 30,40 ", "mouseup 1 0 30,40 ", "auxclick 1 0 30,40 " };
        QTest::newRow("right") << int(Qt::RightButton) << int(Qt::NoModifier)
                               << QStringList { "mousedown 2 2 30,40 ", "mouseup 2 0 30,40 ", "contextmenu 2 2 30,40 " };
    }

    void mouseButtons()
    {
        QFETCH(int, button);
        QFETCH(int, modifiers);
        QFETCH(QStringList, expected);
        QTest::mouseClick(m_view->focusProxy(), Qt::MouseButton(button), Qt::KeyboardModifiers(modifiers), QPoint(30, 40));
        for (const QString& event : expected)
            QTRY_VERIFY2(events(m_view->page()).contains(event), qPrintable(events(m_view->page()).join(QLatin1String(" | "))));
    }

    void doubleClick()
    {
        // Qt turns a double click's second press into a double-click event
        QWidget* target = m_view->focusProxy();
        const QPoint position(70, 20);
        for (QEvent::Type type : { QEvent::MouseButtonPress, QEvent::MouseButtonRelease, QEvent::MouseButtonDblClick, QEvent::MouseButtonRelease }) {
            const Qt::MouseButtons buttons = type == QEvent::MouseButtonRelease ? Qt::NoButton : Qt::LeftButton;
            sendInput(target, QMouseEvent(type, position, target->mapToGlobal(position), Qt::LeftButton, buttons, Qt::NoModifier));
        }
        QTRY_VERIFY2(events(m_view->page()).contains(QStringLiteral("dblclick 0 0 70,20 ")),
            qPrintable(events(m_view->page()).join(QLatin1String(" | "))));
    }

    void mouseMove_data()
    {
        QTest::addColumn<QPoint>("position");
        QTest::newRow("inside") << QPoint(123, 77);
        QTest::newRow("corner") << QPoint(0, 0);
        QTest::newRow("far corner") << QPoint(399, 299);
    }

    void mouseMove()
    {
        QFETCH(QPoint, position);
        moveMouse(position.x() > 200 ? position - QPoint(5, 5) : position + QPoint(5, 5));
        moveMouse(position);
        const QString expected = QStringLiteral("%1,%2").arg(position.x()).arg(position.y());
        QTRY_COMPARE(evaluate(m_view->page(), QStringLiteral("window.lastMove")).toString(), expected);
    }

    void wheel_data()
    {
        QTest::addColumn<QPoint>("angleDelta");
        QTest::addColumn<QPoint>("pixelDelta");
        QTest::addColumn<QString>("expected");
        QTest::addColumn<bool>("scrollsDown");
        QTest::newRow("down") << QPoint(0, -120) << QPoint() << QStringLiteral("wheel 0 1 60,70") << true;
        QTest::newRow("up") << QPoint(0, 120) << QPoint() << QStringLiteral("wheel 0 -1 60,70") << false;
        QTest::newRow("right") << QPoint(-120, 0) << QPoint() << QStringLiteral("wheel 1 0 60,70") << false;
        QTest::newRow("pixel delta down") << QPoint(0, -120) << QPoint(0, -40) << QStringLiteral("wheel 0 1 60,70") << true;
    }

    void wheel()
    {
        QFETCH(QPoint, angleDelta);
        QFETCH(QPoint, pixelDelta);
        QFETCH(QString, expected);
        QFETCH(bool, scrollsDown);
        QWidget* target = m_view->focusProxy();
        const QPointF position(60, 70);
        moveMouse(position.toPoint());
        sendInput(target, QWheelEvent(position, target->mapToGlobal(position), pixelDelta, angleDelta, Qt::NoButton, Qt::NoModifier,
            Qt::NoScrollPhase, false));
        QTRY_VERIFY2(events(m_view->page()).contains(expected), qPrintable(events(m_view->page()).join(QLatin1String(" | "))));
        if (scrollsDown)
            QTRY_VERIFY(evaluate(m_view->page(), QStringLiteral("scrollY")).toInt() > 0);
        else
            QCOMPARE(evaluate(m_view->page(), QStringLiteral("scrollY")).toInt(), 0);
    }

    void keys_data()
    {
        QTest::addColumn<Key>("key");
        QTest::addColumn<int>("modifiers");
        QTest::addColumn<QString>("expected");
        const struct {
            const char* name;
            Key key;
            Qt::KeyboardModifiers modifiers;
            const char* expected;
        } rows[] = {
            { "a", { Qt::Key_A, "a", 38, 0x61 }, Qt::NoModifier, "keydown a " },
            { "shift+A", { Qt::Key_A, "A", 38, 0x41 }, Qt::ShiftModifier, "keydown A S" },
            { "ctrl+Left", { Qt::Key_Left, "", 113, 0xff51 }, Qt::ControlModifier, "keydown ArrowLeft C" },
            { "e acute", { Qt::Key_Eacute, "é", 11, 0xe9 }, Qt::NoModifier, "keydown é " },
            { "cyrillic zhe", { 0x416, "ж", 47, 0x6d6 }, Qt::NoModifier, "keydown ж " },
            { "Backspace", { Qt::Key_Backspace, "\b", 22, 0xff08 }, Qt::NoModifier, "keydown Backspace " },
            { "Escape", { Qt::Key_Escape, "\x1b", 9, 0xff1b }, Qt::NoModifier, "keydown Escape " },
            { "Enter", { Qt::Key_Return, "\r", 36, 0xff0d }, Qt::NoModifier, "keydown Enter " },
            { "Tab", { Qt::Key_Tab, "\t", 23, 0xff09 }, Qt::NoModifier, "keydown Tab " },
            { "Left", { Qt::Key_Left, "", 113, 0xff51 }, Qt::NoModifier, "keydown ArrowLeft " },
            { "Right", { Qt::Key_Right, "", 114, 0xff53 }, Qt::NoModifier, "keydown ArrowRight " },
            { "Up", { Qt::Key_Up, "", 111, 0xff52 }, Qt::NoModifier, "keydown ArrowUp " },
            { "Down", { Qt::Key_Down, "", 116, 0xff54 }, Qt::NoModifier, "keydown ArrowDown " },
            { "F5", { Qt::Key_F5, "", 71, 0xffc2 }, Qt::NoModifier, "keydown F5 " },
        };
        for (const auto& row : rows) {
            QTest::addRow("%s, native codes", row.name) << row.key << int(row.modifiers) << QString::fromUtf8(row.expected);
            Key synthetic = row.key;
            synthetic.scanCode = synthetic.keysym = 0;
            QTest::addRow("%s, synthetic", row.name) << synthetic << int(row.modifiers) << QString::fromUtf8(row.expected);
        }
    }

    void keys()
    {
        QFETCH(Key, key);
        QFETCH(int, modifiers);
        QFETCH(QString, expected);
        QTRY_VERIFY(evaluate(m_view->page(), QStringLiteral("document.hasFocus()")).toBool());
        sendKey(key, Qt::KeyboardModifiers(modifiers));
        QTRY_VERIFY2(events(m_view->page()).contains(expected), qPrintable(events(m_view->page()).join(QLatin1String(" | "))));
    }

    void typing_data()
    {
        QTest::addColumn<bool>("nativeCodes");
        QTest::newRow("native codes") << true;
        QTest::newRow("synthetic") << false;
    }

    void typing()
    {
        QFETCH(bool, nativeCodes);
        evaluate(m_view->page(), QStringLiteral("document.getElementById('input').focus()"));
        QTRY_COMPARE(evaluate(m_view->page(), QStringLiteral("document.activeElement.id")), QVariant(QStringLiteral("input")));
        const Key typed[] = {
            { Qt::Key_A, "a", 38, 0x61 },
            { Qt::Key_Eacute, "é", 11, 0xe9 },
            { 0x416, "ж", 47, 0x6d6 },
            { Qt::Key_Backspace, "\b", 22, 0xff08 },
            { Qt::Key_B, "b", 56, 0x62 },
        };
        for (Key key : typed) {
            if (!nativeCodes)
                key.scanCode = key.keysym = 0;
            sendKey(key, Qt::NoModifier);
        }
        QTRY_COMPARE(evaluate(m_view->page(), QStringLiteral("document.getElementById('input').value")), QVariant(QStringLiteral("aéb")));
    }

    void inputMethod_data()
    {
        QTest::addColumn<QString>("preedit");
        QTest::addColumn<QString>("commit");
        QTest::addColumn<int>("replaced");
        QTest::addColumn<QString>("expected");
        QTest::newRow("commit") << QString() << QStringLiteral("héllo ж") << 0 << QStringLiteral("abhéllo ж");
        QTest::newRow("preedit, then commit") << QStringLiteral("ni") << QStringLiteral("你") << 0 << QStringLiteral("ab你");
        QTest::newRow("replacing the word before") << QString() << QStringLiteral("cd") << 2 << QStringLiteral("cd");
    }

    // Text from an input method, such as an on-screen keyboard's
    void inputMethod()
    {
        QFETCH(QString, preedit);
        QFETCH(QString, commit);
        QFETCH(int, replaced);
        QFETCH(QString, expected);
        evaluate(m_view->page(), QStringLiteral("const input = document.getElementById('input'); input.value = 'ab'; input.focus()"));
        QTRY_COMPARE(evaluate(m_view->page(), QStringLiteral("document.activeElement.id")), QVariant(QStringLiteral("input")));
        QWidget* target = m_view->focusProxy();
        if (!preedit.isEmpty()) {
            QInputMethodEvent composing(preedit, { { QInputMethodEvent::Cursor, int(preedit.size()), 1, QVariant() } });
            QApplication::sendEvent(target, &composing);
            QTRY_COMPARE(evaluate(m_view->page(), QStringLiteral("document.getElementById('input').value")),
                QVariant(QStringLiteral("ab") + preedit));
        }
        QInputMethodEvent committing;
        committing.setCommitString(commit, -replaced, replaced);
        QApplication::sendEvent(target, &committing);
        QTRY_COMPARE(evaluate(m_view->page(), QStringLiteral("document.getElementById('input').value")), QVariant(expected));
    }

    void focus()
    {
        QWebEnginePage* page = m_view->page();
        QTRY_COMPARE(evaluate(page, QStringLiteral("document.hasFocus()")), QVariant(true));
        m_other->setFocus();
        QTRY_COMPARE(evaluate(page, QStringLiteral("document.hasFocus()")), QVariant(false));
        QVERIFY(events(page).contains(QStringLiteral("blur")));
        m_view->setFocus();
        QTRY_COMPARE(evaluate(page, QStringLiteral("document.hasFocus()")), QVariant(true));
        QVERIFY(events(page).contains(QStringLiteral("focus")));
    }

    void resize_data()
    {
        QTest::addColumn<QSize>("size");
        QTest::newRow("larger") << QSize(500, 350);
        QTest::newRow("smaller") << QSize(320, 200);
        QTest::newRow("tiny") << QSize(40, 30);
    }

    void resize()
    {
        QFETCH(QSize, size);
        QTRY_COMPARE(evaluate(m_view->page(), QStringLiteral("[innerWidth, innerHeight]")), QVariant(QVariantList { 400, 300 }));
        m_view->resize(size);
        QTRY_COMPARE(evaluate(m_view->page(), QStringLiteral("[innerWidth, innerHeight]")),
            QVariant(QVariantList { size.width(), size.height() }));
    }

    // Sites size their media by it: YouTube caps video at the screen's height
    void screen()
    {
        const QScreen* screen = m_window->screen();
        const QSize size = screen->geometry().size();
        QTRY_COMPARE(evaluate(m_view->page(), QStringLiteral("[screen.width, screen.height, devicePixelRatio]")),
            QVariant(QVariantList { size.width(), size.height(), screen->devicePixelRatio() }));
    }

    void visibility()
    {
        QWebEnginePage* page = m_view->page();
        QTRY_COMPARE(evaluate(page, QStringLiteral("document.visibilityState")), QVariant(QStringLiteral("visible")));
        m_view->hide();
        QTRY_COMPARE(evaluate(page, QStringLiteral("document.visibilityState")), QVariant(QStringLiteral("hidden")));
        m_view->show();
        QTRY_COMPARE(evaluate(page, QStringLiteral("document.visibilityState")), QVariant(QStringLiteral("visible")));
        m_window->hide();
        QTRY_COMPARE(evaluate(page, QStringLiteral("document.visibilityState")), QVariant(QStringLiteral("hidden")));
    }

    void cursor_data()
    {
        QTest::addColumn<QPoint>("position");
        QTest::addColumn<int>("shape");
        QTest::newRow("pointer") << QPoint(250, 50) << int(Qt::PointingHandCursor);
        QTest::newRow("text") << QPoint(250, 150) << int(Qt::IBeamCursor);
        QTest::newRow("crosshair") << QPoint(350, 50) << int(Qt::CrossCursor);
        QTest::newRow("default") << QPoint(100, 100) << int(Qt::ArrowCursor);
    }

    void cursor()
    {
        QFETCH(QPoint, position);
        QFETCH(int, shape);
        moveMouse(QPoint(350, 50));
        moveMouse(QPoint(100, 100));
        moveMouse(position);
        QTRY_COMPARE(int(m_view->focusProxy()->cursor().shape()), shape);
    }

    // A right click on a misspelled word: the menu's request names the word and the dictionary's suggestions,
    // and a suggestion picked replaces the word
    void spellcheck()
    {
        auto* view = new MenuView;
        view->setParent(m_window.get());
        view->setGeometry(0, 0, 400, 300);
        view->show();
        view->raise();
        QWebEnginePage* page = view->page();
        page->profile()->setSpellCheckLanguages({ QStringLiteral("en-US") });
        page->profile()->setSpellCheckEnabled(true);
        QVERIFY(setsHtml(page, QStringLiteral("<div id=edit contenteditable style='font-size:32px; padding:8px'></div>")));
        evaluate(page, QStringLiteral("edit.focus(); document.execCommand('insertText', false, 'I wrote helo there ')"));
        const QVariantList center = evaluate(page, QStringLiteral(
            "const text = edit.firstChild, at = text.data.indexOf('helo'), range = document.createRange();"
            "range.setStart(text, at); range.setEnd(text, at + 4);"
            "const box = range.getBoundingClientRect(); [box.x + box.width / 2, box.y + box.height / 2]")).toList();
        QCOMPARE(center.size(), 2);
        view->setFocus();
        QTest::qWait(spellcheckMs);
        QTest::mouseClick(view->focusProxy(), Qt::RightButton, {}, QPoint(center[0].toInt(), center[1].toInt()));
        QTRY_VERIFY(view->menuSeen);
        const QWebEngineContextMenuRequest* request = view->lastContextMenuRequest();
        QCOMPARE(request->misspelledWord(), QStringLiteral("helo"));
        QVERIFY2(request->spellCheckerSuggestions().contains(QStringLiteral("hello")),
            qPrintable(request->spellCheckerSuggestions().join(QLatin1Char(','))));
        page->replaceMisspelledWord(QStringLiteral("hello"));
        QTRY_COMPARE(evaluate(page, QStringLiteral("edit.textContent.replace(/\\s+/g, ' ').trim()")).toString(),
            QStringLiteral("I wrote hello there"));
        page->profile()->setSpellCheckEnabled(false);
    }

private:
    void moveMouse(QPoint position)
    {
        QWidget* target = m_view->focusProxy();
        sendInput(target, QMouseEvent(QEvent::MouseMove, position, target->mapToGlobal(position), Qt::NoButton, Qt::NoButton, Qt::NoModifier));
        QTRY_COMPARE(evaluate(m_view->page(), QStringLiteral("window.lastMove")).toString(),
            QStringLiteral("%1,%2").arg(position.x()).arg(position.y()));
    }

    void sendKey(const Key& key, Qt::KeyboardModifiers modifiers)
    {
        for (QEvent::Type type : { QEvent::KeyPress, QEvent::KeyRelease })
            sendInput(m_view->focusProxy(), QKeyEvent(type, key.qtKey, modifiers, key.scanCode, key.keysym, 0, key.text));
    }

    std::unique_ptr<QWidget> m_window;
    QWebEngineView* m_view = nullptr;
    QLineEdit* m_other = nullptr;
};

QTEST_MAIN(tst_Widget)
#include "tst_widget.moc"
