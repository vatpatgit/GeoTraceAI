# TerraTrack Quick Start Guide

## 🚀 Get Started in 3 Steps

### 1. Install Dependencies
```bash
npm install
```

### 2. Generate Placeholder Overlays (Optional)
```bash
npm run generate-overlays
```

### 3. Run Development Server
```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) to see the dashboard!

## ✨ Key Features to Demo

1. **Interactive Map**
   - Click anywhere on the map to see confidence values
   - Use zoom controls (top-right) or mouse wheel
   - Click "Draw on Map" in Region Selector to draw polygons
   - Toggle layers (Satellite, Change Mask, Confidence)

2. **Time Slider**
   - Adjust date range with the date inputs
   - Use the scrubber to jump to any date
   - Click Play to animate through dates
   - Watch charts and map update in real-time

3. **Analytics Panel**
   - View metric cards (Area Monitored, Changes, Confidence, Alerts)
   - Explore time-series charts
   - See alert counts over time

4. **Role Switching**
   - Click the role button (bottom-right) to switch between:
     - **Admin**: Full access
     - **Researcher**: Can configure alerts and generate reports
     - **Viewer**: Read-only access

5. **Alerts & Reports**
   - Click "Alerts" in sidebar to configure alert sensitivity
   - Click "Reports" in sidebar to generate reports
   - Test the alert configuration (simulated)

## 🎨 UI Highlights

- **Dark Theme**: Space/mission-control aesthetic
- **Smooth Animations**: Framer Motion transitions
- **Responsive**: Works on desktop, tablet, and mobile
- **Accessible**: ARIA labels and keyboard navigation

## 📝 Notes for Demo

- All data is **mock data** (no real API calls)
- Map uses **canvas placeholder** (not real satellite tiles)
- Polygon drawing **stores locally** (not saved to backend)
- Alert/Report features are **UI-only** (simulated)

## 🔧 Next Steps for Production

See `README.md` for detailed integration guide:
- Replace mock API with real backend
- Integrate Mapbox/Leaflet for real map tiles
- Add authentication
- Implement real alert/report generation

---

**Ready to demo!** 🎉

