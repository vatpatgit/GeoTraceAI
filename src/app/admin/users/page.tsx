import ProtectedRoute from '@/components/ProtectedRoute'
import AdminUsersClient from '@/components/AdminUsersClient'

export default function AdminUsersPage() {
    return <ProtectedRoute adminOnly><div className="min-h-screen bg-background text-white"><AdminUsersClient /></div></ProtectedRoute>
}
