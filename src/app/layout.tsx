import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import 'maplibre-gl/dist/maplibre-gl.css'
import './globals.css'
import AppShell from '@/components/shell/AppShell'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'GeoTrace - Satellite change intelligence',
  description: 'Bi-temporal satellite change detection: upload or acquire imagery, detect and explore changes on a 3D globe and 2D map, alert, analyse and export.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  )
}
