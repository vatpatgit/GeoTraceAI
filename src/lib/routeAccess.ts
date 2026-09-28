import type { UserRole } from '@/types'

export type ProtectedRouteState = 'loading' | 'login' | 'allowed' | 'forbidden'

export function getProtectedRouteState(
  authStatus: 'loading' | 'authenticated' | 'unauthenticated',
  role: UserRole | null,
  adminOnly = false,
): ProtectedRouteState {
  if (authStatus === 'loading') return 'loading'
  if (authStatus === 'unauthenticated' || !role) return 'login'
  if (adminOnly && role !== 'Admin') return 'forbidden'
  return 'allowed'
}