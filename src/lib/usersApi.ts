export type ManagedRole = 'admin' | 'user' | 'viewer' | 'researcher'

export interface ManagedUser {
    id: string
    name: string
    email: string
    role: ManagedRole
    is_active: boolean
    created_at: string
}

export class UsersApiError extends Error {
    constructor(public status: number, message: string) {
        super(message)
    }
}

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '')

function getHeaders(): HeadersInit {
    const token = typeof window === 'undefined' ? null : localStorage.getItem('terratrack_access_token')
    return {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
    }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    let response: Response
    try {
        response = await fetch(`${API_BASE}${path}`, {
            ...init,
            headers: { ...getHeaders(), ...init.headers },
        })
    } catch {
        throw new UsersApiError(0, 'Unable to reach the user-management service.')
    }

    if (!response.ok) {
        let message = `User-management request failed (${response.status}).`
        try {
            const payload = await response.json()
            if (typeof payload.detail === 'string') message = payload.detail
        } catch {
            // Preserve the status-based message when the server has no JSON detail.
        }
        throw new UsersApiError(response.status, message)
    }

    if (response.status === 204) return undefined as T
    return response.json() as Promise<T>
}

export function listUsers(): Promise<ManagedUser[]> {
    return request<ManagedUser[]>('/users/')
}

export function createUser(input: { name: string; email: string; password: string; role: ManagedRole }): Promise<ManagedUser> {
    return request<ManagedUser>('/users/', { method: 'POST', body: JSON.stringify(input) })
}

export function updateUser(id: string, input: { name: string; email: string }): Promise<ManagedUser> {
    return request<ManagedUser>(`/users/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(input) })
}

export function updateUserRole(id: string, role: ManagedRole): Promise<ManagedUser> {
    return request<ManagedUser>(`/users/${encodeURIComponent(id)}/role`, { method: 'PATCH', body: JSON.stringify({ role }) })
}

export function updateUserStatus(id: string, is_active: boolean): Promise<ManagedUser> {
    return request<ManagedUser>(`/users/${encodeURIComponent(id)}/status`, { method: 'PATCH', body: JSON.stringify({ is_active }) })
}

export function deleteUser(id: string): Promise<void> {
    return request<void>(`/users/${encodeURIComponent(id)}`, { method: 'DELETE' })
}
