import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api/client'
import type { DownloadItem } from '../api/types'
import { formatEta, formatPercent, formatSize, formatSpeed } from '../format'

const POLL_MS = 3000

export function DownloadsPage() {
  const [items, setItems] = useState<DownloadItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<DownloadItem | null>(null)
  const mounted = useRef(true)

  const load = useCallback(async () => {
    try {
      const response = await api.downloads()
      if (!mounted.current) return
      setItems(response.downloads)
      setError(null)
    } catch (err) {
      if (!mounted.current) return
      setError(err instanceof ApiError ? err.message : 'Nem sikerült lekérni a letöltéseket.')
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    void load()
    // Egyszerű polling - nem kell teljes oldalfrissítés.
    const timer = window.setInterval(() => void load(), POLL_MS)
    return () => {
      mounted.current = false
      window.clearInterval(timer)
    }
  }, [load])

  async function act(item: DownloadItem, action: 'pause' | 'resume') {
    setBusy(item.hash)
    try {
      await (action === 'pause' ? api.pause(item.hash) : api.resume(item.hash))
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'A művelet nem sikerült.')
    } finally {
      setBusy(null)
    }
  }

  async function remove(item: DownloadItem, deleteFiles: boolean) {
    setBusy(item.hash)
    setConfirmDelete(null)
    try {
      await api.remove(item.hash, deleteFiles)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'A törlés nem sikerült.')
    } finally {
      setBusy(null)
    }
  }

  return (
    <>
      <h2 style={{ fontSize: '1.15rem', margin: '0 0 16px' }}>Letöltések</h2>

      {error && <div className="message error">{error}</div>}

      {items === null && (
        <div className="empty">
          <span className="spinner" /> Betöltés…
        </div>
      )}

      {items !== null && items.length === 0 && (
        <div className="empty">
          Jelenleg nincs letöltés.
          <br />
          Keress rá egy filmre a Keresés fülön.
        </div>
      )}

      {items?.map((item) => {
        const done = item.progress >= 1
        return (
          <article className="card" key={item.hash}>
            <h3>{item.name}</h3>

            <div className={`progress${done ? ' done' : ''}`}>
              <div style={{ width: `${Math.min(100, item.progress * 100)}%` }} />
            </div>

            <div className="meta">
              <span className="chip size">{formatPercent(item.progress)}</span>
              <span className="chip">{item.state_label}</span>
              <span className="chip">
                {formatSize(item.downloaded_bytes)} / {formatSize(item.size_bytes)}
              </span>
              {!done && (
                <>
                  <span className="chip seed">↓ {formatSpeed(item.dlspeed)}</span>
                  <span className="chip">↑ {formatSpeed(item.upspeed)}</span>
                  <span className="chip">Hátralévő: {formatEta(item.eta_seconds)}</span>
                </>
              )}
              {done && <span className="chip">↑ {formatSpeed(item.upspeed)}</span>}
            </div>

            <div className="card-actions">
              {item.is_paused ? (
                <button
                  type="button"
                  className="small"
                  onClick={() => void act(item, 'resume')}
                  disabled={busy === item.hash}
                >
                  Folytatás
                </button>
              ) : (
                <button
                  type="button"
                  className="small"
                  onClick={() => void act(item, 'pause')}
                  disabled={busy === item.hash}
                >
                  Szüneteltetés
                </button>
              )}
              <button
                type="button"
                className="small danger"
                onClick={() => setConfirmDelete(item)}
                disabled={busy === item.hash}
              >
                Törlés
              </button>
            </div>
          </article>
        )
      })}

      {confirmDelete && (
        <div className="modal-backdrop" onClick={() => setConfirmDelete(null)}>
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            onClick={(event) => event.stopPropagation()}
          >
            <h2>Torrent törlése</h2>
            <div className="field">
              <div className="field-label">Torrent</div>
              <div className="field-value">{confirmDelete.name}</div>
            </div>
            <p className="hint">
              A „Csak a torrent” gomb a letöltött fájlokat a helyükön hagyja, csak a listából
              távolítja el.
            </p>
            <div className="modal-actions">
              <button type="button" onClick={() => setConfirmDelete(null)}>
                Mégsem
              </button>
              <button
                type="button"
                className="primary"
                onClick={() => void remove(confirmDelete, false)}
              >
                Csak a torrent
              </button>
            </div>
            <div className="modal-actions">
              <button
                type="button"
                className="danger"
                onClick={() => {
                  if (
                    window.confirm('Biztosan törlöd a torrentet és a fájlokat?')
                  ) {
                    void remove(confirmDelete, true)
                  }
                }}
              >
                Torrent és fájlok törlése
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
