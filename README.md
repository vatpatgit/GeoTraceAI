# TerraTrack - AI Satellite Monitoring Dashboard

A production-quality frontend prototype for AI satellite monitoring and change detection. This is a **demo for stakeholders** — it uses local mock data only (no API keys, no backend). The focus is on UI, interactions, and realistic map/analytics UX.

## 🚀 Quick Start

### Prerequisites

- Node.js 18+ and npm/yarn/pnpm

### Installation

```bash
# Install dependencies
npm install

# Run development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

### Build for Production

```bash
npm run build
npm start
```

## 📁 Project Structure

```
├── src/
│   ├── app/              # Next.js app router pages
│   ├── components/       # React components
│   │   ├── Dashboard.tsx
│   │   ├── MapViewer.tsx
│   │   ├── AnalyticsPanel.tsx
│   │   ├── TimeSlider.tsx
│   │   ├── LayerToggle.tsx
│   │   ├── RegionSelector.tsx
│   │   ├── AlertConfigurator.tsx
│   │   ├── ReportDownloader.tsx
│   │   └── AuthMock.tsx
│   ├── store/            # Zustand state management
│   ├── lib/              # Utilities and mock API
│   └── types/            # TypeScript interfaces
├── public/
│   └── mocks/            # Mock data files
│       ├── regions.json
│       ├── timeseries.json
│       ├── changes.json
│       ├── confidence.json
│       └── overlays/     # Placeholder overlay images
└── README.md
```

## 🎨 Features

### Core Dashboard
- **Left Sidebar**: Navigation (Dashboard, Regions, Analytics, Alerts, Reports, Settings)
- **Top Header**: Search, notifications, dark mode toggle, user menu
- **Map Viewer**: Interactive map with zoom/pan, polygon drawing, layer overlays
- **Analytics Panel**: Metric cards, time-series charts, bar charts, heatmaps
- **Time Slider**: Dual-date range selector with play/pause animation
- **Floating Controls**: Region selector, layer toggles, export view

### Interactive Features
- **Map Interactions**: Click to view confidence, draw polygons, zoom/pan
- **Time Scrubbing**: Animate through dates, update map overlays and charts
- **Layer Toggles**: Show/hide satellite, change mask, confidence overlays
- **Region Selection**: Dropdown selector + "draw on map" functionality
- **Comparison Mode**: Side-by-side or swipe comparison of two dates
- **Export**: Download current map view as PNG
- **Role-Based UI**: Admin/Researcher/Viewer roles with different permissions

### Mock Data System
All data is fetched from `/public/mocks/` to simulate API calls:
- `regions.json` - List of monitoring regions
- `timeseries.json` - Time-series data per region
- `changes.json` - Change polygons by date
- `confidence.json` - Pixel confidence grid
- `overlays/{regionId}/{date}-{layer}.png` - Raster overlay images

## 🔧 Integration Guide

### Replacing Mock Data with Real API

1. **Update API Client** (`src/lib/mockApi.ts`):
   ```typescript
   // Replace:
   const API_BASE = '/mocks'
   
   // With:
   const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api/v1'
   ```

2. **Update Fetch Functions**:
   - Remove `TODO` comments and implement actual API endpoints
   - Add authentication headers if required
   - Handle error responses appropriately

3. **Update TypeScript Interfaces** (`src/types/index.ts`):
   - Match your backend API response formats
   - Add any additional fields returned by the API

### Integrating Mapbox/Leaflet

The current `MapViewer` uses a canvas-based placeholder. To integrate real map tiles:

1. **Install Mapbox GL JS**:
   ```bash
   npm install mapbox-gl
   ```

2. **Update MapViewer.tsx**:
   ```typescript
   import mapboxgl from 'mapbox-gl'
   import 'mapbox-gl/dist/mapbox-gl.css'
   
   // Replace canvas rendering with:
   useEffect(() => {
     const map = new mapboxgl.Map({
       container: mapContainerRef.current,
       style: 'mapbox://styles/mapbox/satellite-v9',
       center: mapView.center,
       zoom: mapView.zoom,
     })
     
     // Add custom overlay layers
     map.addSource('changes', {
       type: 'raster',
       tiles: [`${API_BASE}/tiles/{z}/{x}/{y}.png`],
       tileSize: 256,
     })
     
     return () => map.remove()
   }, [mapView])
   ```

3. **For Leaflet**:
   ```bash
   npm install leaflet react-leaflet
   ```
   See [Leaflet documentation](https://leafletjs.com/) for integration.

### Adding Overlay Images

Place overlay images in `public/mocks/overlays/{regionId}/{YYYY-MM-DD}-{layer}.png`:
- `changeMask` - Change detection overlay
- `confidence` - Confidence heatmap overlay
- `satellite` - Base satellite imagery (if not using Mapbox)

Or update `getOverlayUrl()` in `src/lib/mockApi.ts` to point to your tile service:
```typescript
export function getOverlayUrl(regionId: string, date: string, layer: string): string {
  return `/tiles/${regionId}/${date}/${layer}/{z}/{x}/{y}.png`
}
```

### Backend Integration Checklist

- [ ] Replace `fetchRegions()` with `/api/v1/regions`
- [ ] Replace `fetchTimeSeries()` with `/api/v1/timeseries?region={id}`
- [ ] Replace `fetchChanges()` with `/api/v1/changes?region={id}&date={date}`
- [ ] Replace `fetchConfidence()` with `/api/v1/confidence?region={id}`
- [ ] Add authentication (JWT tokens, session cookies)
- [ ] Implement real alert webhook/email sending
- [ ] Implement real report generation endpoint
- [ ] Add error handling and retry logic
- [ ] Add loading states for all async operations

## 🎨 Styling

- **Theme**: Dark space/mission-control aesthetic
- **Colors**: Background `#0A0F1C`, Accent `#33E1FF`, Slate `#1F2937`
- **Font**: Inter (loaded via Next.js font optimization)
- **Spacing**: 8px grid system
- **Animations**: Framer Motion for transitions

## 📱 Responsive Design

- **Desktop-first**: Optimized for 1920×1080 and larger
- **Tablet**: Analytics panel collapses, single-column layout
- **Mobile**: Stacked layout, simplified controls (<640px)

## ♿ Accessibility

- ARIA labels on all interactive controls
- Keyboard navigation support
- Focus indicators
- Semantic HTML structure

## 🧪 Development Notes

### State Management
Uses Zustand for global state. Store is in `src/store/useAppStore.ts`.

### Component Architecture
- Atomic, reusable components
- Props-based communication
- Clear separation of concerns

### Mock Data Format
See `src/types/index.ts` for TypeScript interfaces matching mock data structure.

## 📝 TODO for Production

1. **Authentication**: Replace `AuthMock` with real auth (NextAuth.js, Auth0, etc.)
2. **Error Handling**: Add comprehensive error boundaries and retry logic
3. **Performance**: Optimize map rendering, implement virtual scrolling for large datasets
4. **Testing**: Add unit tests (Jest) and E2E tests (Playwright)
5. **Documentation**: Add Storybook for component documentation
6. **CI/CD**: Set up GitHub Actions for automated testing and deployment

## 🐛 Known Limitations (Demo Only)

- Map uses canvas placeholder, not real satellite tiles
- Polygon drawing stores coordinates locally only
- Export generates canvas snapshot, not actual map export
- Alert configuration doesn't send real emails/webhooks
- Report generation simulates processing, doesn't create real PDFs
- All data is static mock data, doesn't update in real-time

## 📄 License

This is a prototype/demo. License TBD.

## 🤝 Contributing

This is a stakeholder demo. For production development, follow your team's contribution guidelines.

---

**Built with**: Next.js 14, TypeScript, TailwindCSS, Recharts, Zustand, Framer Motion, Lucide Icons

