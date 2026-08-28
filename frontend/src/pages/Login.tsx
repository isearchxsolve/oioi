import { FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '@/lib/api'

export function Login() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await api.login(email, password)
      navigate('/', { replace: true })
    } catch {
      setError('Email or password is incorrect. Your studio operator creates all accounts.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="min-h-screen bg-dark-950 flex items-center justify-center p-6">
      <form onSubmit={submit} className="w-full max-w-md rounded-2xl border border-dark-700 bg-dark-900 p-8 shadow-2xl">
        <p className="text-sm font-semibold tracking-widest text-primary-400">OIIOII FILM KIT</p>
        <h1 className="mt-3 text-3xl font-bold text-white">Studio sign in</h1>
        <p className="mt-3 text-sm text-dark-300">Accounts are created by the studio operator after purchase. There is no public signup.</p>
        <label className="mt-7 block text-sm font-medium text-dark-100">
          Email
          <input className="mt-2 w-full rounded-lg border border-dark-600 bg-dark-950 px-3 py-2 text-white outline-none focus:border-primary-400"
            type="email" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} required />
        </label>
        <label className="mt-4 block text-sm font-medium text-dark-100">
          Password
          <input className="mt-2 w-full rounded-lg border border-dark-600 bg-dark-950 px-3 py-2 text-white outline-none focus:border-primary-400"
            type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} required />
        </label>
        {error && <p role="alert" className="mt-4 text-sm text-red-400">{error}</p>}
        <button className="mt-6 w-full rounded-lg bg-primary-500 px-4 py-2 font-semibold text-white disabled:opacity-50" disabled={submitting}>
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </main>
  )
}
