import type {
  DownloadStartedResponse,
  DownloadsResponse,
  SearchResponse,
  SimpleMessage,
  TorrentDetailsResponse,
  UserInfo,
} from './types'

/**
 * A frontend KIZÁRÓLAG a saját backendjét hívja - soha nem az nCore-t vagy a
 * qBittorrentet közvetlenül. Így tracker- és qBittorrent-hitelesítő adat
 * sosem kerül a böngészőbe.
 */

/** Hiba, amelynek üzenete már magyar és a felhasználónak megmutatható. */
export class ApiError extends Error {
  code: string
  status: number

  constructor(message: string, code: string, status: number) {
    super(message)
    this.code = code
    this.status = status
  }
}

function readCsrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)cs_csrf=([^;]*)/)
  return match ? decodeURIComponent(match[1]) : ''
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase()
  const headers = new Headers(init.headers)

  if (init.body !== undefined) headers.set('Content-Type', 'application/json')
  // Cookie alapú auth mellett dupla-submit CSRF token.
  if (method !== 'GET' && method !== 'HEAD') headers.set('X-CSRF-Token', readCsrfToken())

  let response: Response
  try {
    response = await fetch(path, { ...init, headers, credentials: 'same-origin' })
  } catch {
    throw new ApiError('Nem sikerült elérni a szervert. Ellenőrizd a kapcsolatot.', 'network', 0)
  }

  if (response.status === 204) return undefined as T

  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    body = null
  }

  if (!response.ok) {
    const detail = body as { message?: string; code?: string; detail?: unknown } | null
    let message = detail?.message
    if (!message && response.status === 422) message = 'Adj meg legalább 2 karaktert a kereséshez.'
    throw new ApiError(
      message ?? 'Hiba történt. Próbáld újra.',
      detail?.code ?? 'error',
      response.status,
    )
  }

  return body as T
}

export const api = {
  login: (username: string, password: string) =>
    request<UserInfo>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),

  logout: () => request<SimpleMessage>('/api/auth/logout', { method: 'POST' }),

  me: () => request<UserInfo>('/api/auth/me'),

  search: (query: string) =>
    request<SearchResponse>(`/api/search?q=${encodeURIComponent(query)}`),

  torrentDetails: (id: string) =>
    request<TorrentDetailsResponse>(`/api/torrents/${encodeURIComponent(id)}`),

  startDownload: (id: string) =>
    request<DownloadStartedResponse>(`/api/torrents/${encodeURIComponent(id)}/download`, {
      method: 'POST',
    }),

  downloads: () => request<DownloadsResponse>('/api/downloads'),

  pause: (hash: string) =>
    request<SimpleMessage>(`/api/downloads/${encodeURIComponent(hash)}/pause`, { method: 'POST' }),

  resume: (hash: string) =>
    request<SimpleMessage>(`/api/downloads/${encodeURIComponent(hash)}/resume`, { method: 'POST' }),

  remove: (hash: string, deleteFiles: boolean) =>
    request<SimpleMessage>(
      `/api/downloads/${encodeURIComponent(hash)}?delete_files=${deleteFiles}`,
      { method: 'DELETE' },
    ),
}
