import { useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'

interface Props {
  onLoggedIn: (username: string) => void
}

export function LoginPage({ onLoggedIn }: Props) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const user = await api.login(username, password)
      setPassword('')
      onLoggedIn(user.username)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'A bejelentkezés nem sikerült.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-box" onSubmit={onSubmit}>
        <h1>Családi Plex</h1>

        {error && <div className="message error">{error}</div>}

        <label htmlFor="username">Felhasználónév</label>
        <input
          id="username"
          type="text"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          autoComplete="username"
          autoFocus
          required
        />

        <label htmlFor="password">Jelszó</label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="current-password"
          required
        />

        <button type="submit" className="primary" disabled={busy}>
          {busy ? 'Belépés…' : 'Belépés'}
        </button>
      </form>
    </div>
  )
}
