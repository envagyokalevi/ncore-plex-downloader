import { useEffect } from 'react'
import type { TorrentDetailsResponse } from '../api/types'
import { formatSize } from '../format'

interface Props {
  data: TorrentDetailsResponse | null
  loading: boolean
  error: string | null
  starting: boolean
  onConfirm: () => void
  onCancel: () => void
}

/** Megerősítő ablak: mit, mekkorát és hová töltünk le. */
export function ConfirmDownloadModal({
  data,
  loading,
  error,
  starting,
  onConfirm,
  onCancel,
}: Props) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !starting) onCancel()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onCancel, starting])

  const torrent = data?.torrent

  return (
    <div
      className="modal-backdrop"
      onClick={() => {
        if (!starting) onCancel()
      }}
    >
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label="Letöltés megerősítése"
        onClick={(event) => event.stopPropagation()}
      >
        <h2>Letöltés megerősítése</h2>

        {loading && (
          <p className="hint">
            <span className="spinner" /> Adatok betöltése…
          </p>
        )}

        {error && <div className="message error">{error}</div>}

        {torrent && (
          <>
            <div className="field">
              <div className="field-label">Torrent</div>
              <div className="field-value">{torrent.title}</div>
            </div>

            <div className="field">
              <div className="field-label">Méret</div>
              <div className="field-value big">
                {torrent.size_bytes !== null
                  ? formatSize(torrent.size_bytes)
                  : (torrent.size_text ?? 'ismeretlen')}
              </div>
            </div>

            <div className="field">
              <div className="field-label">Letöltési hely</div>
              <div className="field-value">{data.save_path}</div>
              <div className="hint">A qBittorrent alapértelmezett letöltési könyvtára.</div>
            </div>

            {torrent.files.length > 0 && (
              <div className="field">
                <div className="field-label">Fájlok ({torrent.files.length})</div>
                <ul className="file-list">
                  {torrent.files.map((file, index) => (
                    <li key={`${file.name}-${index}`}>
                      <span className="file-name">
                        {file.name}
                        {file.kind ? ` · ${file.kind}` : ''}
                      </span>
                      <span className="file-size">
                        {file.size_bytes !== null
                          ? formatSize(file.size_bytes)
                          : (file.size_text ?? '')}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}

        <div className="modal-actions">
          <button type="button" onClick={onCancel} disabled={starting}>
            Mégsem
          </button>
          <button
            type="button"
            className="primary"
            onClick={onConfirm}
            disabled={starting || loading || !torrent}
          >
            {starting ? 'Indítás…' : 'Letöltés indítása'}
          </button>
        </div>
      </div>
    </div>
  )
}
