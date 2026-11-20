// A download, backed by a WebKitDownload, or a page saved as WebKit saves it; pausing is not supported
#pragma once

#include <QObject>
#include <QUrl>
#include <optional>

class QWebEnginePage;
class QWebEngineProfile;
typedef struct _WebKitDownload WebKitDownload;

class QWebEngineDownloadRequest : public QObject {
    Q_OBJECT
public:
    enum DownloadState { DownloadRequested, DownloadInProgress, DownloadCompleted, DownloadCancelled, DownloadInterrupted };
    Q_ENUM(DownloadState)
    enum SavePageFormat { UnknownSaveFormat = -1, SingleHtmlSaveFormat, CompleteHtmlSaveFormat, MimeHtmlSaveFormat };
    Q_ENUM(SavePageFormat)
    enum DownloadInterruptReason { NoReason = 0, FileFailed = 1, NetworkFailed = 20, UserCanceled = 40 };
    Q_ENUM(DownloadInterruptReason)

    ~QWebEngineDownloadRequest() override;

    quint32 id() const { return m_id; }
    DownloadState state() const { return m_state; }
    qint64 totalBytes() const;
    qint64 receivedBytes() const;
    QUrl url() const;
    QString mimeType() const;
    bool isFinished() const { return m_state >= DownloadCompleted; }
    bool isPaused() const { return false; }
    SavePageFormat savePageFormat() const;
    void setSavePageFormat(SavePageFormat format);
    DownloadInterruptReason interruptReason() const { return m_interruptReason; }
    QString interruptReasonString() const { return m_interruptReasonString; }
    bool isSavePageDownload() const;
    QString suggestedFileName() const { return m_suggestedFileName; }
    QString downloadDirectory() const { return m_downloadDirectory; }
    void setDownloadDirectory(const QString& directory);
    QString downloadFileName() const { return m_downloadFileName; }
    void setDownloadFileName(const QString& fileName);
    QWebEnginePage* page() const;

public Q_SLOTS:
    void accept();
    void cancel();
    void pause() { }
    void resume() { }

Q_SIGNALS:
    void stateChanged(QWebEngineDownloadRequest::DownloadState state);
    void savePageFormatChanged();
    void receivedBytesChanged();
    void totalBytesChanged();
    void interruptReasonChanged();
    void isFinishedChanged();
    void isPausedChanged();
    void downloadDirectoryChanged();
    void downloadFileNameChanged();

private:
    friend class QWebEngineProfile;
    // WebKit's signal handlers
    struct DownloadSignals;
    friend struct DownloadSignals;

    QWebEngineDownloadRequest(WebKitDownload* download, QWebEngineProfile* profile);
    void setState(DownloadState state);
    // The page as shown, in WebKit's one format of it, in place of the download of the page as served
    void saveAsMhtml(const QString& path);

    WebKitDownload* m_download;
    quint32 m_id;
    DownloadState m_state = DownloadRequested;
    DownloadInterruptReason m_interruptReason = NoReason;
    QString m_interruptReasonString;
    QString m_suggestedFileName;
    QString m_downloadDirectory;
    QString m_downloadFileName;
    // Picked by the application; until then, Save Page's own
    std::optional<SavePageFormat> m_savePageFormat;
};
