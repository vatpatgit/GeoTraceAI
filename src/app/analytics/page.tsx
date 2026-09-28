import ProtectedRoute from '@/components/ProtectedRoute'
import RoutePlaceholder from '@/components/RoutePlaceholder'

export default function AnalyticsPage() {
    return <ProtectedRoute><RoutePlaceholder title="Analytics" description="Select a region and date range to view environmental trends." /></ProtectedRoute>
}
