import ProtectedRoute from '@/components/ProtectedRoute'
import RoutePlaceholder from '@/components/RoutePlaceholder'

export default function ReportsPage() {
    return <ProtectedRoute><RoutePlaceholder title="Reports" description="Generate reports for selected regions and date ranges." /></ProtectedRoute>
}
