import { useEffect, useState } from 'react'
import { NavLink, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { api, ApiError } from './api/client'
import { LoginPage } from './pages/LoginPage'
import { SearchPage } from './pages/SearchPage'
import { DownloadsPage } from './pages/DownloadsPage'

export function App() {
  const [user, setUser] = useState<string | null>(null)
  const [checking, setChecking] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    // Van-e élő session? (a session cookie HttpOnly, a JS nem látja)
    api
      .me()
      .then((info) => setUser(info.username))
      .catch(() => setUser(null))
      .finally(() => setChecking(false))
  }, [])

  async function logout() {
    try {
      await api.logout()
    } catch (err) {
      if (!(err instanceof ApiError)) throw err
    }
    setUser(null)
    navigate('/')
  }

  if (checking) {
    return (
      <div className="empty" style={{ paddingTop: 80 }}>
        <span className="spinner" /> Betöltés…
      </div>
    )
  }

  if (!user) {
    return <LoginPage onLoggedIn={setUser} />
  }

  return (
    <div className="app">
      <header className="topbar">
        <h1>Családi Plex</h1>
        <nav>
          <NavLink to="/" end className={({ isActive }) => (isActive ? 'tab active' : 'tab')}>
            Keresés
          </NavLink>
          <NavLink
            to="/downloads"
            className={({ isActive }) => (isActive ? 'tab active' : 'tab')}
          >
            Letöltések
          </NavLink>
        </nav>
        <button type="button" className="small" onClick={() => void logout()}>
          Kilépés
        </button>
      </header>

      <main className="content">
        <Routes>
          <Route path="/" element={<SearchPage />} />
          <Route path="/downloads" element={<DownloadsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}
