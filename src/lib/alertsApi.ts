export interface BackendAlert {
    id: string
    alert_config_id: string
    change_event_id: string
    severity: string
    message: string
    is_read: boolean
    created_at: string
    region_id?: string | null
    coordinates?: [number, number] | null
}

export class AlertsApiError extends Error {
    constructor(public status: number, message: string) {
        super(message)
    }
}

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '')

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const token = typeof window === 'undefined' ? null : localStorage.getItem('terratrack_access_token')
    let response: Response
    try {
        response = await fetch(`${API_BASE}${path}`, {
            ...init,
            headers: {
                'Content-Type': 'application/json',
                ...(token ? { Authorization: `Bearer ${token}` } : {}),
                ...init.headers,
            },
        })
    } catch {
        throw new AlertsApiError(0, 'Unable to reach the alert service.')
    }

    if (!response.ok) {
        let message = `Alert request failed (${response.status}).`
        try {
            const body = await response.json()
            if (typeof body.detail === 'string') message = body.detail
        } catch {
            // Keep the status-based message.
        }
        throw new AlertsApiError(response.status, message)
    }

    return response.status === 204 ? undefined as T : response.json() as Promise<T>
}

export function listAlerts(): Promise<{ alerts: BackendAlert[]; total: number; unread: number }> {
    return request('/alerts/')
}

export function dismissAlert(id: string): Promise<BackendAlert> {
    return request(`/alerts/${encodeURIComponent(id)}/dismiss`, { method: 'POST' })
}
