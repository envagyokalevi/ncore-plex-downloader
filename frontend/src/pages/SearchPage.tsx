import { useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import type { SearchResult, TorrentDetailsResponse } from '../api/types'
import { formatSize } from '../format'
import { ConfirmDownloadModal } from '../components/ConfirmDownloadModal'

export function SearchPage() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[] | null>(null)
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const [selected, setSelected] = useState<SearchResult | null>(null)
  const [details, setDetails] = useState<TorrentDetailsResponse | null>(null)
  const [detailsLoading, setDetailsLoading] = useState(false)
  const [detailsError, setDetailsError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)

  async function onSearch(event: FormEvent) {
    event.preventDefault()
    const trimmed = query.trim()
    if (trimmed.length < 2) {
      setError('Adj meg legalább 2 karaktert.')
      return
    }
    setSearching(true)
    setError(null)
    setNotice(null)
    try {
      const response = await api.search(trimmed)
      setResults(response.results)
    } catch (err) {
      setResults(null)
      setError(err instanceof ApiError ? err.message : 'Hiba történt a keresés során.')
    } finally {
      setSearching(false)
    }
  }

  async function openConfirm(result: SearchResult) {
    setSelected(result)
    setDetails(null)
    setDetailsError(null)
    setDetailsLoading(true)
    try {
      setDetails(await api.torrentDetails(result.id))
    } catch (err) {
      setDetailsError(err instanceof ApiError ? err.message : 'Nem sikerült betölteni az adatokat.')
    } finally {
      setDetailsLoading(false)
    }
  }

  async function confirmDownload() {
    if (!selected) return
    setStarting(true)
    setDetailsError(null)
    try {
      const response = await api.startDownload(selected.id)
      setSelected(null)
      setNotice(response.message)
    } catch (err) {
      setDetailsError(err instanceof ApiError ? err.message : 'Nem sikerült elindítani a letöltést.')
    } finally {
      setStarting(false)
    }
  }

  return (
    <>
      <form className="search-form" onSubmit={onSearch}>
        <label htmlFor="q" className="sr-label" style={{ width: '100%' }}>
          Film neve:
        </label>
        <input
          id="q"
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="pl. Interstellar"
          autoComplete="off"
          autoFocus
          enterKeyHint="search"
        />
        <button type="submit" className="primary" disabled={searching}>
          {searching ? 'Keresés…' : 'Keresés'}
        </button>
      </form>

      {error && <div className="message error" style={{ marginTop: 16 }}>{error}</div>}
      {notice && <div className="message success" style={{ marginTop: 16 }}>{notice}</div>}

      {results !== null && (
        <div style={{ marginTop: 20 }}>
          {results.length === 0 ? (
            <div className="empty">
              Nincs találat.
              <br />
              Próbáld meg más címmel, például eredeti (angol) néven.
            </div>
          ) : (
            <>
              <p className="hint" style={{ marginBottom: 12 }}>
                Találatok: {results.length}
              </p>
              {results.map((result) => (
                <article className="card" key={result.id}>
                  <h3>{result.title}</h3>
                  <div className="meta">
                    <span className="chip size">
                      {result.size_bytes !== null
                        ? formatSize(result.size_bytes)
                        : (result.size_text ?? '? méret')}
                    </span>
                    {result.seeders !== null && (
                      <span className="chip seed">{result.seeders} seed</span>
                    )}
                    {result.leechers !== null && (
                      <span className="chip leech">{result.leechers} leech</span>
                    )}
                    {result.language && <span className="chip">{result.language}</span>}
                    {result.category && <span className="chip">{result.category}</span>}
                  </div>
                  <div className="card-actions">
                    <button type="button" className="primary" onClick={() => openConfirm(result)}>
                      Letöltés
                    </button>
                  </div>
                </article>
              ))}
            </>
          )}
        </div>
      )}

      {results === null && !error && (
        <div className="empty">
          Írd be a film címét, és nyomd meg a Keresés gombot.
        </div>
      )}

      {selected && (
        <ConfirmDownloadModal
          data={details}
          loading={detailsLoading}
          error={detailsError}
          starting={starting}
          onConfirm={confirmDownload}
          onCancel={() => setSelected(null)}
        />
      )}
    </>
  )
}
