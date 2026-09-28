import ProtectedRoute from '@/components/ProtectedRoute'
import RoutePlaceholder from '@/components/RoutePlaceholder'

export default function ChangesPage() {
    return <ProtectedRoute><RoutePlaceholder title="Changes" description="Review detected environmental changes across monitored regions." /></ProtectedRoute>
}
