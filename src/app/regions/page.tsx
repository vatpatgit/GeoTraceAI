import ProtectedRoute from '@/components/ProtectedRoute'
import RoutePlaceholder from '@/components/RoutePlaceholder'
import RegionDirectory from '@/components/RegionDirectory'

export default function RegionsPage() {
    return <ProtectedRoute><div className="min-h-screen bg-background text-white"><RegionDirectory /></div></ProtectedRoute>
}
