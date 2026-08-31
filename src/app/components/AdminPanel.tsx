'use client';

import { useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api-client';

type Props = { onClose: () => void; initialUser: any; onProfileUpdated: (user: any) => void };

async function payload(response: Response) {
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(body?.detail || `HTTP ${response.status}`);
  return body;
}

export default function AdminPanel({ onClose, initialUser, onProfileUpdated }: Props) {
  const [profile, setProfile] = useState(initialUser);
  const [users, setUsers] = useState<any[]>([]);
  const [history, setHistory] = useState<any[]>([]);
  const [message, setMessage] = useState('');
  const [newUser, setNewUser] = useState({ email: '', name: '', password: '' });
  const [passwords, setPasswords] = useState({ current_password: '', new_password: '' });

  const load = async () => {
    try {
      const me = await payload(await apiFetch('/api/v1/auth/me'));
      setProfile(me); onProfileUpdated(me);
      if (me.is_admin) {
        const [userList, allHistory] = await Promise.all([
          payload(await apiFetch('/api/v1/auth/users')),
          payload(await apiFetch('/api/v1/auth/history')),
        ]);
        setUsers(userList.users ?? []); setHistory(allHistory.users ?? []);
      }
    } catch (error: any) { setMessage(error.message); }
  };
  useEffect(() => { load(); }, []);

  const createUser = async (event: React.FormEvent) => {
    event.preventDefault(); setMessage('');
    try {
      await payload(await apiFetch('/api/v1/auth/users', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(newUser) }));
      setNewUser({ email: '', name: '', password: '' }); setMessage('Customer account created.'); await load();
    } catch (error: any) { setMessage(error.message); }
  };
  const updateProfile = async (event: React.FormEvent) => {
    event.preventDefault(); setMessage('');
    try { const next = await payload(await apiFetch('/api/v1/auth/me', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: profile.email, name: profile.name ?? '' }) })); setProfile(next); onProfileUpdated(next); setMessage('Profile updated.'); } catch (error: any) { setMessage(error.message); }
  };
  const changePassword = async (event: React.FormEvent) => {
    event.preventDefault(); setMessage('');
    try { await payload(await apiFetch('/api/v1/auth/me/password', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(passwords) })); setPasswords({ current_password: '', new_password: '' }); setMessage('Password changed. Sign in again on every device.'); } catch (error: any) { setMessage(error.message); }
  };

  return <div className="fixed inset-0 z-[100] overflow-y-auto bg-black/75 p-4 backdrop-blur-sm"><div className="mx-auto my-8 max-w-5xl rounded-2xl border border-slate-700 bg-[#10121b] p-6 text-slate-100 shadow-2xl"><div className="mb-6 flex items-center justify-between"><div><h2 className="text-xl font-bold">{profile?.is_admin ? 'Studio Administration' : 'My Account'}</h2><p className="text-sm text-slate-400">Profile, access, and durable customer delivery history.</p></div><button onClick={onClose} className="rounded-lg border border-slate-700 px-3 py-1 text-sm">Close</button></div>{message && <p className="mb-4 rounded-lg border border-cyan-800 bg-cyan-950/40 p-3 text-sm text-cyan-100">{message}</p>}<div className="grid gap-6 lg:grid-cols-2"><form onSubmit={updateProfile} className="space-y-3 rounded-xl border border-slate-800 p-4"><h3 className="font-semibold">My profile</h3><input value={profile?.email ?? ''} onChange={e => setProfile({ ...profile, email: e.target.value })} className="w-full rounded bg-slate-950 p-2" placeholder="Email"/><input value={profile?.name ?? ''} onChange={e => setProfile({ ...profile, name: e.target.value })} className="w-full rounded bg-slate-950 p-2" placeholder="Display name"/><button className="rounded bg-indigo-600 px-3 py-2 text-sm">Save profile</button></form><form onSubmit={changePassword} className="space-y-3 rounded-xl border border-slate-800 p-4"><h3 className="font-semibold">Change password</h3><input required type="password" value={passwords.current_password} onChange={e => setPasswords({ ...passwords, current_password: e.target.value })} className="w-full rounded bg-slate-950 p-2" placeholder="Current password"/><input required minLength={12} type="password" value={passwords.new_password} onChange={e => setPasswords({ ...passwords, new_password: e.target.value })} className="w-full rounded bg-slate-950 p-2" placeholder="New password (12+ characters)"/><button className="rounded bg-indigo-600 px-3 py-2 text-sm">Change password</button></form></div>{profile?.is_admin && <><div className="mt-6 grid gap-6 lg:grid-cols-2"><form onSubmit={createUser} className="space-y-3 rounded-xl border border-emerald-900/70 bg-emerald-950/20 p-4"><h3 className="font-semibold">Create customer credentials</h3><input required type="email" value={newUser.email} onChange={e => setNewUser({ ...newUser, email: e.target.value })} className="w-full rounded bg-slate-950 p-2" placeholder="Customer email"/><input value={newUser.name} onChange={e => setNewUser({ ...newUser, name: e.target.value })} className="w-full rounded bg-slate-950 p-2" placeholder="Customer name"/><input required minLength={12} type="password" value={newUser.password} onChange={e => setNewUser({ ...newUser, password: e.target.value })} className="w-full rounded bg-slate-950 p-2" placeholder="Initial password (12+ characters)"/><button className="rounded bg-emerald-600 px-3 py-2 text-sm">Create customer</button></form><div className="rounded-xl border border-slate-800 p-4"><h3 className="font-semibold">Customers ({users.length})</h3><div className="mt-3 max-h-52 space-y-2 overflow-auto">{users.map(user => <div key={user.id} className="rounded bg-slate-900 p-2 text-sm"><span>{user.name || user.email}</span><span className="ml-2 text-slate-400">{user.email}</span><span className="float-right text-xs text-emerald-400">{user.is_active ? 'active' : 'disabled'}</span></div>)}</div></div></div><div className="mt-6 rounded-xl border border-slate-800 p-4"><h3 className="font-semibold">All customer history</h3><div className="mt-3 max-h-72 space-y-3 overflow-auto">{history.map(entry => <div key={entry.user.id} className="rounded bg-slate-900 p-3 text-sm"><div className="font-medium">{entry.user.email}</div><div className="mt-1 text-slate-400">{entry.projects.length} projects · {entry.assets.length} assets · {entry.films.length} films · {entry.storage.artifact_count} retained deliverables</div></div>)}</div></div></>}</div></div>;
}
