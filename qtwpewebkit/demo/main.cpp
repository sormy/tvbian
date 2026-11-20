// A tabbed shell to try QtWpeWebKit's widget before a real browser uses it
#include "webwidget.h"

#include <QApplication>
#include <QCommandLineParser>
#include <QFile>
#include <QDebug>
#include <QLineEdit>
#include <QMainWindow>
#include <QTabWidget>
#include <QToolBar>
#include <QToolButton>
#include <wpe/webkit.h>

static QUrl urlFromInput(const QString& text)
{
    return QUrl::fromUserInput(text.trimmed());
}

int main(int argc, char** argv)
{
    QCoreApplication::setAttribute(Qt::AA_ShareOpenGLContexts);
    QApplication app(argc, argv);
    QCommandLineParser options;
    const QCommandLineOption userAgent("user-agent", "The user agent pages see.", "string");
    options.addOption(userAgent);
    const QCommandLineOption userScript("user-script", "A script run in every page once it loaded.", "file");
    options.addOption(userScript);
    options.addPositionalArgument("url", "The page to open.");
    options.addHelpOption();
    options.process(app);

    QMainWindow window;
    auto* tabs = new QTabWidget;
    auto* address = new QLineEdit;
    auto* newTab = new QToolButton;
    newTab->setText("+");
    tabs->setTabsClosable(true);
    tabs->setCornerWidget(newTab);
    auto* toolbar = window.addToolBar("Navigation");
    toolbar->addWidget(address);
    window.setCentralWidget(tabs);

    auto current = [tabs] { return static_cast<QtWpeWebKit::WebWidget*>(tabs->currentWidget()); };
    auto openTab = [&](const QUrl& url) {
        auto* page = new QtWpeWebKit::WebWidget;
        if (options.isSet(userScript)) {
            QFile file(options.value(userScript));
            if (!file.open(QIODevice::ReadOnly))
                qFatal("cannot read %s", qPrintable(file.fileName()));
            WebKitUserScript* script = webkit_user_script_new(file.readAll().constData(),
                WEBKIT_USER_CONTENT_INJECT_TOP_FRAME, WEBKIT_USER_SCRIPT_INJECT_AT_DOCUMENT_END, nullptr, nullptr);
            webkit_user_content_manager_add_script(webkit_web_view_get_user_content_manager(page->webView()), script);
            webkit_user_script_unref(script);
        }
        if (options.isSet(userAgent))
            webkit_settings_set_user_agent(webkit_web_view_get_settings(page->webView()),
                qPrintable(options.value(userAgent)));
        const int index = tabs->addTab(page, url.host());
        QObject::connect(page, &QtWpeWebKit::WebWidget::titleChanged, tabs, [tabs, page](const QString& title) {
            tabs->setTabText(tabs->indexOf(page), title.left(48));
            // tests read a page's progress from its title
            qInfo().noquote() << "title:" << title;
        });
        QObject::connect(page, &QtWpeWebKit::WebWidget::urlChanged, address, [tabs, page, address](const QUrl& url) {
            if (tabs->currentWidget() == page)
                address->setText(url.toString());
        });
        tabs->setCurrentIndex(index);
        page->load(url);
        page->setFocus();
    };

    QObject::connect(address, &QLineEdit::returnPressed, [&] {
        if (auto* page = current()) {
            page->load(urlFromInput(address->text()));
            page->setFocus();
        }
    });
    QObject::connect(tabs, &QTabWidget::currentChanged, [&] {
        if (auto* page = current())
            address->setText(page->url().toString());
    });
    QObject::connect(tabs, &QTabWidget::tabCloseRequested, [tabs](int index) {
        delete tabs->widget(index);
    });
    QObject::connect(newTab, &QToolButton::clicked, [&] { openTab(QUrl("about:blank")); });

    const QStringList urls = options.positionalArguments();
    openTab(urlFromInput(urls.value(0, "https://wpewebkit.org")));
    window.resize(1280, 720);
    window.show();
    return app.exec();
}
