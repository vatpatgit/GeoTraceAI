/**
 * Historical mock dataset for TerraTrack GIS Intelligence Layer.
 * Provides multi-region, multi-date, multi-metric data for the dynamic dashboard.
 * All data is generated deterministically — same inputs always produce same outputs.
 */

// ─── Types ──────────────────────────────────────────────────────────────────────

export interface HistoricalMetrics {
  date: string
  regionId: string
  forestLossKm2: number
  ndviIndex: number
  temperatureC: number
  fireAlerts: number
  floodRisk: number
  confidence: number
}

export interface HistoricalSummary {
  areaMonitored: string
  totalChange: string
  changePerDay: string
  trend: 'increasing' | 'decreasing' | 'stable'
  confidence: string
  activeAlerts: number
  criticalAlerts: number
  forestLoss: string
  ndvi: string
  temperature: string
  floodRisk: string
}

export interface HistoricalAlert {
  id: string
  type: 'deforestation' | 'wildfire' | 'flood' | 'urban'
  severity: 'critical' | 'warning' | 'info'
  title: string
  description: string
  timestamp: string
  coordinates: [number, number]
  confidence: number
  status: 'active' | 'monitoring' | 'resolved'
}

// ─── Helper Functions ────────────────────────────────────────────────────────────

function seededRandom(seed: number): number {
  const x = Math.sin(seed) * 10000
  return x - Math.floor(x)
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

// ─── Constants & Configuration ───────────────────────────────────────────────────

interface RegionConfig {
  seedBase: number
  areaKm2: number
  tempBase: number
  ndviBase: number
  forestLossBase: number
  floodBase: number
  center: [number, number]
  scale: number
}

const REGION_CONFIGS: Record<string, RegionConfig> = {
  'region-1': { seedBase: 42, areaKm2: 1250000, tempBase: 28, ndviBase: 0.72, forestLossBase: 8, floodBase: 25, center: [-65.0, -2.5], scale: 1.5 },
  'region-2': { seedBase: 137, areaKm2: 980000, tempBase: 26, ndviBase: 0.68, forestLossBase: 5, floodBase: 30, center: [23.0, 0.0], scale: 1.2 },
  'region-3': { seedBase: 256, areaKm2: 743000, tempBase: 30, ndviBase: 0.55, forestLossBase: 7, floodBase: 20, center: [113.5, 1.5], scale: 1.0 },
  'region-4': { seedBase: 389, areaKm2: 540000, tempBase: 35, ndviBase: 0.35, forestLossBase: 3, floodBase: 15, center: [0.0, 15.0], scale: 0.8 },
  'region-5': { seedBase: 512, areaKm2: 2040000, tempBase: 27, ndviBase: 0.58, forestLossBase: 10, floodBase: 22, center: [-47.5, -12.5], scale: 1.3 },
}

const DATES: string[] = []
for (let i = 1; i <= 30; i++) {
  DATES.push(`2024-01-${i.toString().padStart(2, '0')}`)
}

// ─── Data Generation ─────────────────────────────────────────────────────────────

const historicalDataCache: Record<string, HistoricalMetrics[]> = {}

function generateData() {
  for (const [regionId, config] of Object.entries(REGION_CONFIGS)) {
    const metrics: HistoricalMetrics[] = []
    
    for (let i = 0; i < DATES.length; i++) {
      const date = DATES[i]
      const daySeed = config.seedBase + i
      
      const rForest = seededRandom(daySeed + 1)
      const rNdvi = seededRandom(daySeed + 2)
      const rTemp = seededRandom(daySeed + 3)
      const rFire = seededRandom(daySeed + 4)
      const rFlood = seededRandom(daySeed + 5)
      const rConf = seededRandom(daySeed + 6)
      
      metrics.push({
        date,
        regionId,
        forestLossKm2: config.forestLossBase + rForest * 15,
        ndviIndex: clamp(config.ndviBase - rNdvi * 0.15, 0, 1),
        temperatureC: config.tempBase + rTemp * 6 - 2,
        fireAlerts: Math.floor(rFire * 8 * config.scale),
        floodRisk: clamp(config.floodBase + rFlood * 30, 0, 100),
        confidence: 0.72 + rConf * 0.25
      })
    }
    
    historicalDataCache[regionId] = metrics
  }
}

// Initialize cache
generateData()

// ─── API Functions ───────────────────────────────────────────────────────────────

export function getHistoricalData(regionId: string, date: string): HistoricalMetrics | null {
  const regionData = historicalDataCache[regionId]
  if (!regionData) return null
  return regionData.find(d => d.date === date) || null
}

export function getHistoricalRange(regionId: string, startDate: string, endDate: string): HistoricalMetrics[] {
  const regionData = historicalDataCache[regionId]
  if (!regionData) return []
  return regionData.filter(d => d.date >= startDate && d.date <= endDate)
}

export function getHistoricalSummary(regionId: string, date: string): HistoricalSummary {
  const config = REGION_CONFIGS[regionId] || REGION_CONFIGS['region-1']
  const regionData = historicalDataCache[regionId] || []
  
  const targetIndex = regionData.findIndex(d => d.date === date)
  const upToDateData = targetIndex >= 0 ? regionData.slice(0, targetIndex + 1) : regionData
  
  const totalLoss = upToDateData.reduce((sum, d) => sum + d.forestLossKm2, 0)
  const avgLoss = upToDateData.length > 0 ? totalLoss / upToDateData.length : 0
  
  let trend: 'increasing' | 'decreasing' | 'stable' = 'stable'
  if (upToDateData.length >= 10) {
    const first5 = upToDateData.slice(0, 5)
    const last5 = upToDateData.slice(-5)
    const avgFirst = first5.reduce((sum, d) => sum + d.forestLossKm2, 0) / 5
    const avgLast = last5.reduce((sum, d) => sum + d.forestLossKm2, 0) / 5
    
    if (avgLast > avgFirst * 1.05) trend = 'increasing'
    else if (avgLast < avgFirst * 0.95) trend = 'decreasing'
  }
  
  const currentMetrics = getHistoricalData(regionId, date) || (regionData.length > 0 ? regionData[regionData.length - 1] : {
    forestLossKm2: 0, ndviIndex: 0, temperatureC: 0, fireAlerts: 0, floodRisk: 0, confidence: 0
  })
  
  const avgConf = upToDateData.length > 0 
    ? upToDateData.reduce((sum, d) => sum + d.confidence, 0) / upToDateData.length 
    : currentMetrics.confidence
    
  return {
    areaMonitored: `${(config.areaKm2 / 1000).toFixed(0)}K km²`,
    totalChange: `${totalLoss.toFixed(1)} km²`,
    changePerDay: `${avgLoss.toFixed(2)} km²/day`,
    trend,
    confidence: `${(avgConf * 100).toFixed(1)}%`,
    activeAlerts: currentMetrics.fireAlerts,
    criticalAlerts: Math.floor(currentMetrics.fireAlerts * 0.3),
    forestLoss: `${currentMetrics.forestLossKm2.toFixed(1)} km²`,
    ndvi: currentMetrics.ndviIndex.toFixed(3),
    temperature: `${currentMetrics.temperatureC.toFixed(1)}°C`,
    floodRisk: `${currentMetrics.floodRisk.toFixed(0)}/100`
  }
}

export function getHistoricalAlerts(regionId: string, date: string): HistoricalAlert[] {
  const config = REGION_CONFIGS[regionId]
  if (!config) return []
  
  const dayParts = date.split('-')
  const dayOfMonth = dayParts.length >= 3 ? parseInt(dayParts[2], 10) : 1
  const seed = config.seedBase + dayOfMonth * 31
  
  const rCount = seededRandom(seed)
  const numAlerts = Math.floor(rCount * 4) + 1 // 1 to 4 alerts
  
  const alerts: HistoricalAlert[] = []
  
  for (let i = 0; i < numAlerts; i++) {
    const alertSeed = seed + i * 10
    const rType = seededRandom(alertSeed + 1)
    const rSeverity = seededRandom(alertSeed + 2)
    const rLat = seededRandom(alertSeed + 3)
    const rLng = seededRandom(alertSeed + 4)
    const rConf = seededRandom(alertSeed + 5)
    
    let type: HistoricalAlert['type'] = 'deforestation'
    if (rType < 0.4) type = 'wildfire'
    else if (rType < 0.7) type = 'deforestation'
    else if (rType < 0.9) type = 'flood'
    else type = 'urban'
    
    let severity: HistoricalAlert['severity'] = 'info'
    if (rSeverity < 0.2) severity = 'critical'
    else if (rSeverity < 0.6) severity = 'warning'
    
    const latOffset = (rLat - 0.5) * 2
    const lngOffset = (rLng - 0.5) * 2
    
    let status: HistoricalAlert['status'] = 'active'
    if (dayOfMonth < 10) status = 'resolved'
    else if (dayOfMonth < 20) status = 'monitoring'
    
    alerts.push({
      id: `alert-${regionId}-${date}-${i}`,
      type,
      severity,
      title: `${type.charAt(0).toUpperCase() + type.slice(1)} Alert`,
      description: `Detected potential ${type} activity in monitored zone.`,
      timestamp: `${date}T${Math.floor(seededRandom(alertSeed + 6) * 24).toString().padStart(2, '0')}:${Math.floor(seededRandom(alertSeed + 7) * 60).toString().padStart(2, '0')}:00Z`,
      coordinates: [config.center[0] + lngOffset, config.center[1] + latOffset],
      confidence: 0.6 + rConf * 0.38,
      status
    })
  }
  
  return alerts
}
