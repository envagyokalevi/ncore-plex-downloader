export interface SearchResult {
  id: string
  title: string
  size_bytes: number | null
  size_text: string | null
  category: string | null
  language: string | null
  seeders: number | null
  leechers: number | null
}

export interface SearchResponse {
  query: string
  count: number
  results: SearchResult[]
}

export interface TorrentFile {
  name: string
  size_bytes: number | null
  size_text: string | null
  kind: string | null
}

export interface TorrentDetails {
  id: string
  title: string
  size_bytes: number | null
  size_text: string | null
  category: string | null
  language: string | null
  seeders: number | null
  leechers: number | null
  files: TorrentFile[]
}

export interface TorrentDetailsResponse {
  torrent: TorrentDetails
  /** A qBittorrentben beállított alapértelmezett letöltési könyvtár. */
  save_path: string
}

export interface DownloadStartedResponse {
  message: string
  torrent_hash: string | null
}

export interface DownloadItem {
  hash: string
  name: string
  /** 0.0 - 1.0 */
  progress: number
  state: string
  state_label: string
  size_bytes: number | null
  downloaded_bytes: number | null
  dlspeed: number | null
  upspeed: number | null
  eta_seconds: number | null
  save_path: string | null
  is_paused: boolean
}

export interface DownloadsResponse {
  downloads: DownloadItem[]
}

export interface UserInfo {
  username: string
}

export interface SimpleMessage {
  message: string
}
