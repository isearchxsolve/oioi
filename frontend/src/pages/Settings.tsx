import { FormEvent, useEffect, useState } from 'react'
import { api } from '@/lib/api'

type StudioUser = {
  id: string
  email: string
  name?: string | null
  avatar_url?: string | null
  is_active: boolean
  is_admin: boolean
}

export function Settings() {
  const [profile, setProfile] = useState<StudioUser | null>(null)
  const [users, setUsers] = useState<StudioUser[]>([])
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    api.getCurrentUser().then(async user => {
      setProfile(user)
      if (user.is_admin) {
        const response = await api.listManagedUsers()
        setUsers(response.users)
      }
    }).catch(() => undefined)
  }, [])

  async function updateProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!profile) return
    setError('')
    try {
      const updated = await api.updateUserProfile({ email: profile.email, name: profile.name || '', avatar_url: profile.avatar_url || '' })
      setProfile(updated)
      setMessage('Profile saved.')
    } catch {
      setError('Unable to save profile.')
    }
  }

  async function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const fields = new FormData(event.currentTarget)
    const current = String(fields.get('currentPassword') || '')
    const next = String(fields.get('newPassword') || '')
    setError('')
    try {
      await api.changeMyPassword(current, next)
      window.location.assign('/login')
    } catch {
      setError('Unable to change password. It must be at least 12 characters and your current password must match.')
    }
  }

  async function createUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const fields = new FormData(event.currentTarget)
    setError('')
    try {
      const user = await api.createManagedUser({
        email: String(fields.get('email') || ''), password: String(fields.get('password') || ''),
        name: String(fields.get('name') || '') || undefined,
      })
      setUsers(existing => [user, ...existing])
      event.currentTarget.reset()
      setMessage('Customer credentials created. Send them privately to the customer.')
    } catch {
      setError('Unable to create the customer. Check the email and use a unique password of at least 12 characters.')
    }
  }

  if (!profile) return <p className="text-dark-300">Loading your studio profile…</p>

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <header><h1 className="text-3xl font-bold text-white">Studio settings</h1><p className="mt-2 text-dark-300">Manage your profile, password, and operator-created customer accounts.</p></header>
      {message && <p className="rounded-lg bg-emerald-950 p-3 text-emerald-300">{message}</p>}
      {error && <p role="alert" className="rounded-lg bg-red-950 p-3 text-red-300">{error}</p>}
      <form onSubmit={updateProfile} className="rounded-xl border border-dark-700 bg-dark-900 p-6 space-y-4">
        <h2 className="text-xl font-semibold text-white">My profile</h2>
        <label className="block text-sm text-dark-200">Email<input className="mt-1 w-full rounded bg-dark-950 p-2 text-white" type="email" value={profile.email} onChange={event => setProfile({ ...profile, email: event.target.value })} required /></label>
        <label className="block text-sm text-dark-200">Name<input className="mt-1 w-full rounded bg-dark-950 p-2 text-white" value={profile.name || ''} onChange={event => setProfile({ ...profile, name: event.target.value })} /></label>
        <button className="rounded bg-primary-500 px-4 py-2 font-semibold text-white">Save profile</button>
      </form>
      <form onSubmit={changePassword} className="rounded-xl border border-dark-700 bg-dark-900 p-6 space-y-4">
        <h2 className="text-xl font-semibold text-white">Change password</h2>
        <input className="w-full rounded bg-dark-950 p-2 text-white" name="currentPassword" type="password" placeholder="Current password" required />
        <input className="w-full rounded bg-dark-950 p-2 text-white" name="newPassword" type="password" minLength={12} placeholder="New password (12+ characters)" required />
        <button className="rounded bg-primary-500 px-4 py-2 font-semibold text-white">Change password</button>
      </form>
      {profile.is_admin && <>
        <form onSubmit={createUser} className="rounded-xl border border-primary-700 bg-dark-900 p-6 space-y-4">
          <h2 className="text-xl font-semibold text-white">Create paid customer</h2>
          <p className="text-sm text-dark-300">This is the only account-creation route. Customers cannot sign themselves up.</p>
          <input className="w-full rounded bg-dark-950 p-2 text-white" name="name" placeholder="Customer name (optional)" />
          <input className="w-full rounded bg-dark-950 p-2 text-white" name="email" type="email" placeholder="Customer email" required />
          <input className="w-full rounded bg-dark-950 p-2 text-white" name="password" type="password" minLength={12} placeholder="Initial password (12+ characters)" required />
          <button className="rounded bg-primary-500 px-4 py-2 font-semibold text-white">Create customer credentials</button>
        </form>
        <section className="rounded-xl border border-dark-700 bg-dark-900 p-6"><h2 className="text-xl font-semibold text-white">Customer accounts</h2>
          <ul className="mt-4 space-y-2">{users.filter(user => !user.is_admin).map(user => <li key={user.id} className="flex justify-between rounded bg-dark-950 p-3 text-sm text-dark-200"><span>{user.name || user.email}</span><span>{user.is_active ? 'Active' : 'Disabled'}</span></li>)}</ul>
        </section>
      </>}
    </div>
  )
}
