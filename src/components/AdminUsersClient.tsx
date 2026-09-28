'use client'

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AlertCircle, Check, Loader2, Plus, Search, Shield, Trash2, UserRound, X } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { useAppStore } from '@/store/useAppStore'
import {
    createUser,
    deleteUser,
    listUsers,
    ManagedRole,
    ManagedUser,
    updateUser,
    updateUserRole,
    updateUserStatus,
    UsersApiError,
} from '@/lib/usersApi'

const roles: { value: ManagedRole; label: string }[] = [
    { value: 'user', label: 'USER' },
    { value: 'viewer', label: 'VIEWER' },
    { value: 'admin', label: 'ADMIN' },
]

function displayRole(role: string): string {
    if (role.toLowerCase() === 'researcher') return 'USER'
    return role.toUpperCase()
}

function errorMessage(error: unknown): string {
    if (error instanceof UsersApiError) {
        if (error.status === 401) return 'Your session has expired. Please sign in again.'
        if (error.status === 403) return 'You do not have permission to manage users.'
        if (error.status >= 500 || error.status === 0) return 'Unable to load users. Please try again.'
        if (error.message.toLowerCase().includes('last')) return 'This action cannot be completed because TerraTrack must retain at least one administrator.'
        return error.message
    }
    return 'Unable to complete the request. Please try again.'
}

export default function AdminUsersClient() {
    const router = useRouter()
    const { authUser, setAuthUser, setAuthStatus } = useAppStore()
    const [users, setUsers] = useState<ManagedUser[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')
    const [query, setQuery] = useState('')
    const [modal, setModal] = useState<'create' | 'edit' | null>(null)
    const [selectedUser, setSelectedUser] = useState<ManagedUser | null>(null)
    const [mutationError, setMutationError] = useState('')
    const [saving, setSaving] = useState(false)
    const createFormRef = useRef<HTMLFormElement>(null)
    const [editName, setEditName] = useState('')
    const [editEmail, setEditEmail] = useState('')
    const [editRole, setEditRole] = useState<ManagedRole>('user')

    const loadUsers = useCallback(async () => {
        setLoading(true)
        setError('')
        try {
            setUsers(await listUsers())
        } catch (requestError) {
            if (requestError instanceof UsersApiError && requestError.status === 401) {
                setAuthUser(null)
                setAuthStatus('unauthenticated')
                router.replace('/dashboard')
                return
            }
            setError(errorMessage(requestError))
        } finally {
            setLoading(false)
        }
    }, [router, setAuthStatus, setAuthUser])

    useEffect(() => {
        loadUsers()
    }, [loadUsers])

    const filteredUsers = useMemo(() => {
        const normalized = query.trim().toLowerCase()
        if (!normalized) return users
        return users.filter((user) => user.name.toLowerCase().includes(normalized) || user.email.toLowerCase().includes(normalized))
    }, [query, users])

    const closeModal = (force = false) => {
        if (!saving || force) {
            setModal(null)
            setSelectedUser(null)
            setMutationError('')
        }
    }

    const openEdit = (user: ManagedUser) => {
        setSelectedUser(user)
        setEditName(user.name)
        setEditEmail(user.email)
        setEditRole(user.role === 'researcher' ? 'user' : user.role)
        setMutationError('')
        setModal('edit')
    }

    const handleCreate = async (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault()
        const form = new FormData(event.currentTarget)
        const name = String(form.get('name') || '').trim()
        const email = String(form.get('email') || '').trim()
        const password = String(form.get('password') || '')
        const role = String(form.get('role') || 'user') as ManagedRole
        if (!name || !email || password.length < 12 || !roles.some((item) => item.value === role)) {
            setMutationError('Enter a name, valid email, password of at least 12 characters, and a valid role.')
            return
        }
        setSaving(true)
        setMutationError('')
        try {
            await createUser({ name, email, password, role })
            closeModal(true)
            await loadUsers()
        } catch (requestError) {
            setMutationError(errorMessage(requestError))
        } finally {
            setSaving(false)
        }
    }

    const handleEdit = async (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault()
        if (!selectedUser || !editName.trim() || !editEmail.trim()) {
            setMutationError('Name and email are required.')
            return
        }
        setSaving(true)
        setMutationError('')
        try {
            await updateUser(selectedUser.id, { name: editName.trim(), email: editEmail.trim() })
            if (editRole !== selectedUser.role) await updateUserRole(selectedUser.id, editRole)
            closeModal(true)
            await loadUsers()
        } catch (requestError) {
            setMutationError(errorMessage(requestError))
        } finally {
            setSaving(false)
        }
    }

    const handleStatus = async (user: ManagedUser) => {
        const nextStatus = !user.is_active
        if (!nextStatus && !window.confirm(`Deactivate ${user.name}? They will no longer be able to sign in.`)) return
        setMutationError('')
        try {
            await updateUserStatus(user.id, nextStatus)
            await loadUsers()
        } catch (requestError) {
            setMutationError(errorMessage(requestError))
        }
    }

    const handleDelete = async (user: ManagedUser) => {
        if (!window.confirm(`Delete ${user.name}? This action cannot be undone.`)) return
        setMutationError('')
        try {
            await deleteUser(user.id)
            await loadUsers()
        } catch (requestError) {
            setMutationError(errorMessage(requestError))
        }
    }

    return (
        <section className="max-w-6xl mx-auto px-6 py-10">
            <div className="flex flex-wrap items-end justify-between gap-5">
                <div>
                    <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-accent"><Shield className="w-4 h-4" /> Administration</div>
                    <h1 className="mt-3 text-3xl font-semibold text-white">User Management</h1>
                    <p className="mt-2 text-sm text-slate-400">Manage TerraTrack users and their access roles.</p>
                </div>
                <button onClick={() => { setMutationError(''); setModal('create') }} className="inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-background hover:bg-accent/90"><Plus className="w-4 h-4" /> Create User</button>
            </div>

            <div className="mt-8 flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
                <div className="relative w-full max-w-sm"><Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search name or email" className="w-full rounded-lg border border-white/10 bg-white/[0.04] py-2 pl-9 pr-3 text-sm text-white placeholder:text-slate-500 focus:border-accent focus:outline-none" aria-label="Search users" /></div>
                {authUser && <div className="text-xs text-slate-400">Current user: <span className="text-slate-200">{authUser.email}</span> <span className="ml-2 text-accent">{displayRole(authUser.role)}</span></div>}
            </div>

            {mutationError && <div className="mt-4 flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200"><AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />{mutationError}</div>}
            {error && <div className="mt-4 flex items-center justify-between rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200"><span className="flex items-center gap-2"><AlertCircle className="h-4 w-4" />{error}</span><button onClick={loadUsers} className="font-semibold text-accent">Try again</button></div>}

            <div className="mt-5 overflow-x-auto rounded-xl border border-white/10 bg-white/[0.02]">
                {loading ? <div className="flex items-center gap-3 p-8 text-sm text-slate-400"><Loader2 className="h-4 w-4 animate-spin text-accent" />Loading users...</div> : filteredUsers.length === 0 ? <div className="p-10 text-center"><UserRound className="mx-auto h-8 w-8 text-slate-600" /><h2 className="mt-3 text-sm font-semibold text-white">No users found</h2><p className="mt-1 text-sm text-slate-500">Create a user to begin managing TerraTrack access.</p></div> : <table className="w-full min-w-[760px] text-left text-sm"><thead className="border-b border-white/10 bg-white/[0.03] text-xs uppercase tracking-wider text-slate-500"><tr><th className="px-5 py-3">Name</th><th className="px-5 py-3">Email</th><th className="px-5 py-3">Role</th><th className="px-5 py-3">Status</th><th className="px-5 py-3">Created</th><th className="px-5 py-3 text-right">Actions</th></tr></thead><tbody className="divide-y divide-white/[0.06]">{filteredUsers.map((user) => <tr key={user.id} className="text-slate-300"><td className="px-5 py-4 font-medium text-white">{user.name}</td><td className="px-5 py-4 text-slate-400">{user.email}</td><td className="px-5 py-4"><span className="rounded-full border border-accent/30 bg-accent/10 px-2 py-1 text-[10px] font-semibold tracking-wider text-accent">{displayRole(user.role)}</span></td><td className="px-5 py-4"><span className={user.is_active ? 'text-emerald-400' : 'text-slate-500'}>{user.is_active ? 'Active' : 'Inactive'}</span></td><td className="px-5 py-4 text-slate-500">{new Date(user.created_at).toLocaleDateString()}</td><td className="px-5 py-4"><div className="flex justify-end gap-2"><button onClick={() => openEdit(user)} className="rounded border border-white/10 px-2.5 py-1.5 text-xs text-slate-300 hover:border-accent/50 hover:text-accent">Edit</button><button onClick={() => handleStatus(user)} className="rounded border border-white/10 px-2.5 py-1.5 text-xs text-slate-300 hover:border-amber-400/50 hover:text-amber-300">{user.is_active ? 'Deactivate' : 'Activate'}</button><button onClick={() => handleDelete(user)} className="rounded border border-red-500/20 p-1.5 text-red-300 hover:bg-red-500/10" aria-label={`Delete ${user.name}`}><Trash2 className="h-4 w-4" /></button></div></td></tr>)}</tbody></table>}
            </div>

            {modal && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true"><div className="w-full max-w-lg rounded-xl border border-white/10 bg-[#111827] p-6 shadow-2xl"><div className="flex items-center justify-between"><h2 className="text-lg font-semibold text-white">{modal === 'create' ? 'Create User' : 'Edit User'}</h2><button onClick={() => closeModal()} className="text-slate-400 hover:text-white" aria-label="Close dialog"><X className="h-5 w-5" /></button></div>{mutationError && <p className="mt-4 rounded border border-red-500/30 bg-red-500/10 p-2 text-sm text-red-200">{mutationError}</p>}{modal === 'create' ? <form ref={createFormRef} onSubmit={handleCreate} className="mt-5 space-y-4"><Field label="Name" name="name" required /><Field label="Email" name="email" type="email" minLength={5} required /><Field label="Password" name="password" type="password" minLength={12} required /><RoleField name="role" defaultValue="user" /><FormActions saving={saving} onCancel={() => closeModal()} /></form> : <form onSubmit={handleEdit} className="mt-5 space-y-4"><Field label="Name" value={editName} onChange={(event) => setEditName(event.target.value)} required /><Field label="Email" type="email" value={editEmail} onChange={(event) => setEditEmail(event.target.value)} required /><RoleField value={editRole} onChange={(event) => setEditRole(event.target.value as ManagedRole)} /><FormActions saving={saving} onCancel={() => closeModal()} /></form>}</div></div>}
        </section>
    )
}

function Field(props: React.InputHTMLAttributes<HTMLInputElement> & { label: string }) { const { label, ...inputProps } = props; return <label className="block text-sm text-slate-300">{label}<input {...inputProps} className="mt-1.5 w-full rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-white placeholder:text-slate-500 focus:border-accent focus:outline-none" /></label> }
function RoleField(props: React.SelectHTMLAttributes<HTMLSelectElement>) { return <label className="block text-sm text-slate-300">Role<select {...props} className="mt-1.5 w-full rounded-lg border border-white/10 bg-[#0d1321] px-3 py-2 text-white focus:border-accent focus:outline-none">{roles.map((role) => <option key={role.value} value={role.value}>{role.label}</option>)}</select></label> }
function FormActions({ saving, onCancel }: { saving: boolean; onCancel: () => void }) { return <div className="flex justify-end gap-3 border-t border-white/10 pt-4"><button type="button" onClick={onCancel} className="rounded-lg border border-white/10 px-4 py-2 text-sm text-slate-300">Cancel</button><button type="submit" disabled={saving} className="inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-background disabled:opacity-50">{saving && <Loader2 className="h-4 w-4 animate-spin" />}{saving ? 'Saving...' : <><Check className="h-4 w-4" />Save</>}</button></div> }
