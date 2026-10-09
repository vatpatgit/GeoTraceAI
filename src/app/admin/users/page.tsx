import AdminOnly from '@/components/auth/AdminOnly'
import AdminUsersClient from '@/components/AdminUsersClient'

export default function AdminUsersPage() {
  return <AdminOnly><div className="h-full overflow-y-auto bg-ink-950"><AdminUsersClient /></div></AdminOnly>
}
