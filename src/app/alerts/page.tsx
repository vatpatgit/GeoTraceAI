import ProtectedRoute from '@/components/ProtectedRoute'
import AlertPanel from '@/components/AlertSystem/AlertPanel'
import Header from '@/components/Header'
import CollapsibleSidebar from '@/components/Layout/CollapsibleSidebar'

export default function AlertsPage() {
    return <ProtectedRoute><div className="flex min-h-screen bg-background text-white"><CollapsibleSidebar /><main className="flex min-w-0 flex-1 flex-col"><Header /><div className="relative min-h-[calc(100vh-3.5rem)]"><AlertPanel /></div></main></div></ProtectedRoute>
}
