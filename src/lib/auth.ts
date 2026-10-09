export type Role = 'admin' | 'user' | 'viewer'

/** Backend roles are lower-case; legacy names ('administrator', 'researcher') are normalised exactly as the server does. */
export function normalizeRole(raw: string | null | undefined): Role {
  const r = (raw ?? '').trim().toLowerCase()
  if (r === 'admin' || r === 'administrator') return 'admin'
  if (r === 'user' || r === 'researcher') return 'user'
  return 'viewer'
}

export const roleLabel: Record<Role, string> = { admin: 'Administrator', user: 'Analyst', viewer: 'Viewer' }
export const canWrite = (role: Role | null | undefined): boolean => role === 'admin' || role === 'user'
export const isAdmin = (role: Role | null | undefined): boolean => role === 'admin'

export type ProtectedRouteState = 'loading' | 'login' | 'allowed' | 'forbidden'

export function getProtectedRouteState(
  authStatus: 'loading' | 'authenticated' | 'unauthenticated',
  role: Role | null,
  adminOnly = false,
): ProtectedRouteState {
  if (authStatus === 'loading') return 'loading'
  if (authStatus === 'unauthenticated' || !role) return 'login'
  if (adminOnly && role !== 'admin') return 'forbidden'
  return 'allowed'
}
