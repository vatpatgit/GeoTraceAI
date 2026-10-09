// Copies CesiumJS runtime assets (workers, widgets, textures) into public/cesium so the globe works offline-first.
// Runs automatically before `dev` and `build` (see package.json).
const fs = require('fs')
const path = require('path')

const src = path.join(__dirname, '..', 'node_modules', 'cesium', 'Build', 'Cesium')
const dest = path.join(__dirname, '..', 'public', 'cesium')
if (!fs.existsSync(src)) {
  console.warn('[copy-cesium] cesium is not installed; skipping (3D globe will be unavailable).')
  process.exit(0)
}
for (const dir of ['Workers', 'ThirdParty', 'Assets', 'Widgets']) {
  const from = path.join(src, dir)
  if (!fs.existsSync(from)) continue
  fs.cpSync(from, path.join(dest, dir), { recursive: true })
}
console.log('[copy-cesium] copied Cesium runtime assets to public/cesium')
