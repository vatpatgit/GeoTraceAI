/**
 * Inline mock data for TerraTrack demo
 * All data is generated deterministically so the demo works without any API/file dependencies
 */

import type { Region, TimeSeriesDataPoint } from '@/types'

export const REGIONS: Region[] = [
  {
    id: 'region-1',
    name: 'Amazon Basin — Northern Sector',
    bbox: { minLon: -70.0, minLat: -5.0, maxLon: -60.0, maxLat: 5.0 },
    defaultDateRange: { start: '2024-01-01', end: '2024-01-30' },
    areaKm2: 1250000,
  },
  {
    id: 'region-2',
    name: 'Congo Rainforest — Central Africa',
    bbox: { minLon: 18.0, minLat: -4.0, maxLon: 28.0, maxLat: 4.0 },
    defaultDateRange: { start: '2024-01-01', end: '2024-01-30' },
    areaKm2: 980000,
  },
  {
    id: 'region-3',
    name: 'Borneo — Southeast Asia',
    bbox: { minLon: 108.0, minLat: -4.0, maxLon: 119.0, maxLat: 7.0 },
    defaultDateRange: { start: '2024-01-01', end: '2024-01-30' },
    areaKm2: 743000,
  },
  {
    id: 'region-4',
    name: 'Sahel Region — West Africa',
    bbox: { minLon: -10.0, minLat: 10.0, maxLon: 10.0, maxLat: 20.0 },
    defaultDateRange: { start: '2024-01-01', end: '2024-01-30' },
    areaKm2: 540000,
  },
  {
    id: 'region-5',
    name: 'Cerrado — Brazil',
    bbox: { minLon: -55.0, minLat: -20.0, maxLon: -40.0, maxLat: -5.0 },
    defaultDateRange: { start: '2024-01-01', end: '2024-01-30' },
    areaKm2: 2040000,
  },
]

// Region center coordinates for map fly-to
export const REGION_CENTERS: Record<string, { center: [number, number]; zoom: number }> = {
  'region-1': { center: [-65.0, -2.5], zoom: 6 },
  'region-2': { center: [23.0, 0.0], zoom: 6 },
  'region-3': { center: [113.5, 1.5], zoom: 6 },
  'region-4': { center: [0.0, 15.0], zoom: 5 },
  'region-5': { center: [-47.5, -12.5], zoom: 5 },
}

// Region-specific colors for charts
export const REGION_THEME: Record<string, { primary: string; gradient: string; alertColor: string }> = {
  'region-1': { primary: '#10B981', gradient: '#10B981', alertColor: '#EF4444' },
  'region-2': { primary: '#8B5CF6', gradient: '#8B5CF6', alertColor: '#F59E0B' },
  'region-3': { primary: '#06B6D4', gradient: '#06B6D4', alertColor: '#EF4444' },
  'region-4': { primary: '#F59E0B', gradient: '#F59E0B', alertColor: '#DC2626' },
  'region-5': { primary: '#EC4899', gradient: '#EC4899', alertColor: '#F97316' },
}

// Seeded pseudo-random for deterministic data
function seededRandom(seed: number): number {
  const x = Math.sin(seed) * 10000
  return x - Math.floor(x)
}

function generateTimeSeries(regionId: string): TimeSeriesDataPoint[] {
  const seedBase: Record<string, number> = {
    'region-1': 42,
    'region-2': 137,
    'region-3': 256,
    'region-4': 389,
    'region-5': 512,
  }
  const base = seedBase[regionId] || 100
  const points: TimeSeriesDataPoint[] = []

  // Multipliers to make different regions have different scales
  const scale: Record<string, number> = {
    'region-1': 1.0,
    'region-2': 0.7,
    'region-3': 0.85,
    'region-4': 0.4,
    'region-5': 1.2,
  }
  const s = scale[regionId] || 1

  for (let day = 1; day <= 30; day++) {
    const r1 = seededRandom(base + day * 7)
    const r2 = seededRandom(base + day * 13)
    const r3 = seededRandom(base + day * 19)

    points.push({
      date: `2024-01-${String(day).padStart(2, '0')}`,
      change_area_km2: parseFloat((3 + r1 * 20 * s).toFixed(1)),
      avg_confidence: parseFloat((0.72 + r2 * 0.25).toFixed(2)),
      alert_count: Math.floor(r3 * 10 * s),
    })
  }

  return points
}

// Pre-generate all time series data
const TIME_SERIES_CACHE: Record<string, TimeSeriesDataPoint[]> = {}
REGIONS.forEach((r) => {
  TIME_SERIES_CACHE[r.id] = generateTimeSeries(r.id)
})

export function getRegions(): Region[] {
  return REGIONS
}

export function getTimeSeries(regionId: string): TimeSeriesDataPoint[] {
  return TIME_SERIES_CACHE[regionId] || []
}

export function getRegionById(regionId: string): Region | undefined {
  return REGIONS.find((r) => r.id === regionId)
}

// Region-specific summary metrics (pre-computed for performance)
export function getRegionSummary(regionId: string) {
  const ts = getTimeSeries(regionId)
  const region = getRegionById(regionId)
  if (!ts.length || !region) return null

  const totalChange = ts.reduce((s, d) => s + d.change_area_km2, 0)
  const avgConfidence = ts.reduce((s, d) => s + d.avg_confidence, 0) / ts.length
  const totalAlerts = ts.reduce((s, d) => s + d.alert_count, 0)
  const maxChange = Math.max(...ts.map((d) => d.change_area_km2))
  const trend = ts[ts.length - 1].change_area_km2 > ts[0].change_area_km2 ? 'increasing' : 'decreasing'

  return {
    regionName: region.name,
    areaKm2: region.areaKm2,
    totalChange: parseFloat(totalChange.toFixed(1)),
    avgConfidence: parseFloat((avgConfidence * 100).toFixed(1)),
    totalAlerts,
    maxChange: parseFloat(maxChange.toFixed(1)),
    trend,
    changePerDay: parseFloat((totalChange / ts.length).toFixed(1)),
  }
}

// Mock alerts for a region
export interface MockAlert {
  id: string
  type: 'deforestation' | 'wildfire' | 'urban' | 'water'
  severity: 'critical' | 'warning' | 'info'
  title: string
  description: string
  timestamp: string
  region: string
  coordinates: [number, number]
}

// ─── Interactive Map Region Definitions ─────────────────────────────────────
// SVG polygons use viewport-percentage coordinates (0-100) for responsive scaling.
// When migrating to Mapbox, replace these with GeoJSON coordinates — interaction
// and data layers remain unchanged.

export interface MapRegion {
  id: string
  name: string
  shortName: string
  /** SVG polygon points as viewport-percentage pairs [x, y][] */
  polygon: [number, number][]
  /** Center for label positioning [x%, y%] */
  center: [number, number]
  /** Region accent color */
  color: string
  /** Alert marker positions relative to viewport [x%, y%][] */
  alertPositions: [number, number][]
  /** Change detection zone: [x%, y%, w%, h%] */
  changeZones: [number, number, number, number][]
}

export const MAP_REGIONS: MapRegion[] = [
  {
    id: 'region-1',
    name: 'Amazon Basin — Northern Sector',
    shortName: 'Amazon Basin',
    polygon: [
      [15, 30], [35, 25], [40, 35], [38, 50], [28, 55], [12, 45],
    ],
    center: [26, 40],
    color: '#10B981',
    alertPositions: [[22, 35], [32, 42], [25, 48]],
    changeZones: [[18, 32, 14, 12], [28, 40, 8, 8]],
  },
  {
    id: 'region-2',
    name: 'Congo Rainforest — Central Africa',
    shortName: 'Congo Rainforest',
    polygon: [
      [42, 28], [58, 26], [62, 38], [58, 50], [45, 48], [40, 38],
    ],
    center: [50, 38],
    color: '#8B5CF6',
    alertPositions: [[48, 34], [55, 42]],
    changeZones: [[44, 30, 12, 10]],
  },
  {
    id: 'region-3',
    name: 'Borneo — Southeast Asia',
    shortName: 'Borneo',
    polygon: [
      [65, 30], [80, 28], [85, 40], [82, 52], [70, 50], [63, 40],
    ],
    center: [74, 40],
    color: '#06B6D4',
    alertPositions: [[72, 36], [78, 44]],
    changeZones: [[68, 34, 10, 10], [76, 42, 6, 6]],
  },
  {
    id: 'region-4',
    name: 'Sahel Region — West Africa',
    shortName: 'Sahel Region',
    polygon: [
      [30, 58], [55, 55], [58, 65], [52, 74], [35, 75], [28, 68],
    ],
    center: [43, 66],
    color: '#F59E0B',
    alertPositions: [[40, 63]],
    changeZones: [[34, 60, 16, 8]],
  },
  {
    id: 'region-5',
    name: 'Cerrado — Brazil',
    shortName: 'Cerrado',
    polygon: [
      [60, 60], [78, 58], [82, 68], [78, 78], [65, 80], [58, 70],
    ],
    center: [70, 69],
    color: '#EC4899',
    alertPositions: [[66, 65], [74, 72]],
    changeZones: [[62, 62, 12, 10]],
  },
]

// ─── AI Insight Generation Engine ───────────────────────────────────────────

export type InsightSeverity = 'high' | 'moderate' | 'informational'
export type InsightType = 'trend' | 'risk' | 'pattern'

export interface AIInsight {
  id: string
  type: InsightType
  severity: InsightSeverity
  title: string
  description: string
  /** Causal explanation — why this insight was generated */
  reasoning: string
  /** Actionable recommendation — what to do about it */
  recommendation: string
  /** Confidence score — how confident the AI model is (0-100) */
  confidence: number
  percentChange: number
  iconHint: 'trending-up' | 'trending-down' | 'alert-triangle' | 'activity' | 'eye'
}

// ─── Mock Environmental Factors (deterministic per region) ──────────────────
// These simulate the environmental context that drives causal reasoning.
// In production, these would come from real sensor/satellite data.

interface EnvironmentalFactors {
  /** Temperature trend: positive = warming, negative = cooling (°C delta) */
  tempDelta: number
  /** Precipitation change: positive = wetter, negative = drier (% delta) */
  precipDelta: number
  /** NDVI vegetation health: 0-1 scale, lower = stressed */
  ndviIndex: number
  /** Human activity pressure: 0-1 scale, higher = more pressure */
  humanPressure: number
  /** Soil moisture: 0-1 scale, lower = drier */
  soilMoisture: number
  /** Primary driver keywords for this region */
  drivers: {
    trend: string[]
    risk: string[]
    pattern: string[]
  }
  /** Actionable recommendations keyed by insight type + severity */
  recommendations: {
    trend: { high: string; moderate: string; low: string }
    risk: { high: string; moderate: string; low: string }
    pattern: string
  }
}

const REGION_FACTORS: Record<string, EnvironmentalFactors> = {
  'region-1': {
    tempDelta: 1.8,
    precipDelta: -22,
    ndviIndex: 0.58,
    humanPressure: 0.72,
    soilMoisture: 0.35,
    drivers: {
      trend: ['prolonged dry season conditions', 'elevated human activity near highway BR-319 and logging corridors'],
      risk: ['NDVI decline of 12% indicating vegetation stress', 'surface temperature anomaly of +1.8°C above seasonal baseline'],
      pattern: ['recurrent spectral signatures matching mechanized clearing', 'proximity to existing road networks and river access points'],
    },
    recommendations: {
      trend: {
        high: 'Deploy rapid-response ground teams to BR-319 corridor. Escalate to IBAMA enforcement division and initiate emergency moratorium on new clearing permits within 50 km buffer.',
        moderate: 'Increase satellite revisit frequency to daily coverage. Issue early-warning notifications to regional environmental officers and flag parcels for next compliance audit cycle.',
        low: 'Continue standard biweekly monitoring cadence. Log change vectors in deforestation registry for quarterly trend report.',
      },
      risk: {
        high: 'Activate fire prevention protocol: pre-position aerial firefighting assets at Manaus and Porto Velho bases. Issue public fire ban and coordinate with ICMBio for protected area patrols.',
        moderate: 'Deploy soil moisture sensors at 5 priority locations. Establish fire watch towers along identified corridor and brief local brigades.',
        low: 'Monitor temperature and precipitation anomalies via INPE dashboard. No immediate field action required.',
      },
      pattern: 'Task field investigation team to validate spectral signatures with ground-truth photography. Cross-reference cleared parcels with CAR registry to identify unlicensed operations.',
    },
  },
  'region-2': {
    tempDelta: 0.9,
    precipDelta: -8,
    ndviIndex: 0.65,
    humanPressure: 0.55,
    soilMoisture: 0.52,
    drivers: {
      trend: ['expansion of artisanal mining concessions into protected buffer zones', 'reduced enforcement coverage during wet-to-dry season transition'],
      risk: ['habitat fragmentation index exceeding critical threshold', 'coltan and gold extraction sites expanding beyond licensed boundaries'],
      pattern: ['sediment plume analysis showing upstream disturbance', 'seasonal water table fluctuations deviating from 10-year average'],
    },
    recommendations: {
      trend: {
        high: 'Coordinate with ICCN rangers for immediate concession boundary enforcement. Request MONUSCO aerial reconnaissance of illegal mining sites and initiate legal proceedings.',
        moderate: 'Increase ranger patrol frequency in buffer zones. Deploy drone surveillance over flagged concession boundaries and document violations.',
        low: 'Update monthly mining concession GIS layers. Share change reports with provincial mining inspectorate.',
      },
      risk: {
        high: 'Initiate emergency habitat corridor restoration protocol. Relocate monitoring camera traps to newly fragmented zones and escalate to CITES advisory.',
        moderate: 'Commission rapid biodiversity assessment in impacted zones. Engage local communities for participatory monitoring.',
        low: 'Continue quarterly habitat integrity assessments. No immediate intervention required.',
      },
      pattern: 'Deploy water quality sensors at 3 tributary junctions to correlate sediment plume data with upstream mining activity. Share findings with Congo Basin Forest Partnership.',
    },
  },
  'region-3': {
    tempDelta: 1.2,
    precipDelta: -15,
    ndviIndex: 0.48,
    humanPressure: 0.81,
    soilMoisture: 0.28,
    drivers: {
      trend: ['systematic drainage canal construction lowering water tables', 'corporate land acquisition patterns correlating with clearing events'],
      risk: ['peat subsidence detected at 2.4 cm/month via InSAR', 'soil moisture below 28% — critical ignition threshold for peatlands'],
      pattern: ['canopy gap analysis showing edge effects propagating inward', 'road network density increase of 18% enabling further encroachment'],
    },
    recommendations: {
      trend: {
        high: 'Issue cease-and-desist to operators draining peatlands. Coordinate with KLHK for moratorium extension on new concessions. Engage palm oil supply chain buyers for compliance pressure.',
        moderate: 'Map all active drainage canals via LiDAR. Flag concessions violating High Conservation Value commitments and notify RSPO certification body.',
        low: 'Track plantation boundary changes quarterly. Update land-use change database for annual sustainability report.',
      },
      risk: {
        high: 'Pre-deploy peatland firefighting foam units to 3 highest-risk zones. Activate community fire brigade network and enforce zero-burning policy with aerial patrols.',
        moderate: 'Install piezometer network for real-time water-table monitoring. Implement canal blocking at 5 priority drainage points.',
        low: 'Continue InSAR subsidence monitoring. Share data with Peatland Restoration Agency for planning.',
      },
      pattern: 'Commission high-resolution UAV canopy survey to quantify edge-effect propagation rates. Model forest fragmentation scenarios for next 5 years under current expansion trajectory.',
    },
  },
  'region-4': {
    tempDelta: 2.3,
    precipDelta: -31,
    ndviIndex: 0.32,
    humanPressure: 0.38,
    soilMoisture: 0.18,
    drivers: {
      trend: ['rainfall deficit of 31% relative to 30-year climatological mean', 'wind erosion index elevated due to reduced ground cover'],
      risk: ['soil moisture at 18% — well below crop viability threshold', 'growing season shortening by 12 days compared to previous decade'],
      pattern: ['vegetation boundary regression rate exceeding 1.2 km/year', 'albedo shift detected in Landsat time series indicating bare soil exposure'],
    },
    recommendations: {
      trend: {
        high: 'Activate drought emergency response: distribute drought-resistant seed stock, coordinate with WFP for food security assessment, and mobilize erosion-control earthworks.',
        moderate: 'Implement assisted regeneration along degraded vegetation strips. Deploy wind-break barriers at 10 priority locations and promote community-managed reforestation.',
        low: 'Continue satellite-based vegetation index monitoring. Share trend data with national desertification observatory.',
      },
      risk: {
        high: 'Issue agricultural advisory for immediate crop protection measures. Coordinate with FEWS NET for food security early warning and activate livestock migration corridors.',
        moderate: 'Deploy soil moisture probes at 8 agro-pastoral stations. Brief extension workers on water-conservation tillage techniques.',
        low: 'Monitor growing season indicators via MODIS phenology products. No immediate agronomic intervention required.',
      },
      pattern: 'Establish permanent vegetation-boundary monitoring transects at 5 km intervals. Compare with Great Green Wall progress data and update desertification risk maps.',
    },
  },
  'region-5': {
    tempDelta: 1.5,
    precipDelta: -18,
    ndviIndex: 0.52,
    humanPressure: 0.68,
    soilMoisture: 0.31,
    drivers: {
      trend: ['commodity price surge driving soybean frontier expansion', 'fire-clearance cycles detected in pre-planting preparation zones'],
      risk: ['consecutive dry days exceeding 45-day threshold', 'biomass combustibility index elevated across 150 km² zone'],
      pattern: ['urban heat island effect expanding into peri-urban Cerrado', 'infrastructure corridor development fragmenting wildlife corridors'],
    },
    recommendations: {
      trend: {
        high: 'Engage soybean traders operating in deforestation-linked supply chains. File compliance reports with Soy Moratorium signatories and flag parcels for PRODES verification.',
        moderate: 'Increase monitoring of fire-clearance buffer zones. Cross-reference DETER alerts with rural property boundaries for compliance auditing.',
        low: 'Track agricultural commodity price correlations with clearing rates. Update land-use forecasting model inputs.',
      },
      risk: {
        high: 'Pre-position ground firefighting crews at 4 high-biomass zones. Activate PREVFOGO aerial assets and coordinate with state civil defense for evacuation readiness.',
        moderate: 'Issue fire risk bulletin to landowners via SMS alert system. Prepare firebreak clearing along critical savanna corridors.',
        low: 'Continue VIIRS active fire monitoring. Share weekly fire risk index with municipal coordinators.',
      },
      pattern: 'Commission urban expansion impact assessment with thermal infrared analysis. Map wildlife corridor fragmentation and propose mitigation measures for environmental licensing agency.',
    },
  },
}

/**
 * Generates deterministic AI insights with causal reasoning by comparing
 * first-half vs second-half of the time series and correlating with
 * environmental factors. No randomness — pure data-driven logic.
 */
export function generateInsights(regionId: string, dateRange?: { start: string; end: string }): AIInsight[] {
  const ts = getTimeSeries(regionId)
  if (!ts.length) return []

  // Filter by date range if provided
  let data = ts
  if (dateRange) {
    data = ts.filter((p) => {
      return p.date >= dateRange.start && p.date <= dateRange.end
    })
  }
  if (data.length < 4) data = ts // fallback to full series

  const mid = Math.floor(data.length / 2)
  const firstHalf = data.slice(0, mid)
  const secondHalf = data.slice(mid)

  // Calculate averages
  const avgFirst = firstHalf.reduce((s, d) => s + d.change_area_km2, 0) / firstHalf.length
  const avgSecond = secondHalf.reduce((s, d) => s + d.change_area_km2, 0) / secondHalf.length
  const percentChange = avgFirst > 0 ? ((avgSecond - avgFirst) / avgFirst) * 100 : 0

  const avgAlertFirst = firstHalf.reduce((s, d) => s + d.alert_count, 0) / firstHalf.length
  const avgAlertSecond = secondHalf.reduce((s, d) => s + d.alert_count, 0) / secondHalf.length
  const alertChange = avgAlertFirst > 0 ? ((avgAlertSecond - avgAlertFirst) / avgAlertFirst) * 100 : 0

  const avgConfSecond = secondHalf.reduce((s, d) => s + d.avg_confidence, 0) / secondHalf.length
  const maxChange = Math.max(...data.map((d) => d.change_area_km2))

  // Environmental factors for reasoning
  const factors = REGION_FACTORS[regionId] || REGION_FACTORS['region-1']

  // Region-specific insight templates
  const regionInsights: Record<string, { trend: string; risk: string; pattern: string }> = {
    'region-1': {
      trend: 'Deforestation',
      risk: 'Wildfire risk detected due to rising temperature patterns',
      pattern: 'Illegal logging activity observed near river corridors',
    },
    'region-2': {
      trend: 'Mining-related clearing',
      risk: 'Biodiversity loss risk from expanding artisanal mining',
      pattern: 'Seasonal flooding pattern shift detected',
    },
    'region-3': {
      trend: 'Palm oil plantation expansion',
      risk: 'Peatland fire risk elevated due to drainage activity',
      pattern: 'Primary forest fragmentation accelerating',
    },
    'region-4': {
      trend: 'Desertification advance',
      risk: 'Drought stress intensifying across vegetation belt',
      pattern: 'Sahel boundary shifting south beyond historical range',
    },
    'region-5': {
      trend: 'Agricultural conversion',
      risk: 'Dry season fire risk elevated across savanna zones',
      pattern: 'Urban expansion observed in northern region',
    },
  }

  const templates = regionInsights[regionId] || regionInsights['region-1']
  const direction = percentChange >= 0 ? 'increased' : 'decreased'
  const absChange = Math.abs(parseFloat(percentChange.toFixed(1)))

  // ── Build causal reasoning strings ────────────────────────────────────

  // Trend reasoning: combines environmental conditions + human factors
  const trendReasoning = buildTrendReasoning(factors, direction, absChange, templates.trend)

  // Risk reasoning: combines environmental stress indicators
  const riskReasoning = buildRiskReasoning(factors, avgAlertSecond, alertChange)

  // Pattern reasoning: combines detection methodology + spatial analysis
  const patternReasoning = buildPatternReasoning(factors, avgConfSecond, data.length)

  // ── Build recommendations ─────────────────────────────────────────────

  const trendSeverity: InsightSeverity = absChange > 15 ? 'high' : absChange > 5 ? 'moderate' : 'informational'
  const riskSeverity: InsightSeverity = avgAlertSecond > 5 ? 'high' : avgAlertSecond > 3 ? 'moderate' : 'informational'

  const trendRecommendation = buildRecommendation(factors, 'trend', trendSeverity)
  const riskRecommendation = buildRecommendation(factors, 'risk', riskSeverity)
  const patternRecommendation = factors.recommendations.pattern

  // ── Compute confidence scores ─────────────────────────────────────────
  // Blend observation count, detection model confidence, and data consistency
  const trendConfidence = computeConfidence(avgConfSecond, data.length, absChange)
  const riskConfidence = computeConfidence(avgConfSecond, data.length, Math.abs(alertChange))
  const patternConfidence = computeConfidence(avgConfSecond, data.length, 0)

  const insights: AIInsight[] = [
    // 1. Trend insight
    {
      id: `${regionId}-trend`,
      type: 'trend',
      severity: trendSeverity,
      title: `${templates.trend} ${direction} by ${absChange}%`,
      description: `${templates.trend} has ${direction} by ${absChange}% over the selected monitoring period. Peak daily change reached ${maxChange.toFixed(1)} km².`,
      reasoning: trendReasoning,
      recommendation: trendRecommendation,
      confidence: trendConfidence,
      percentChange: parseFloat(percentChange.toFixed(1)),
      iconHint: percentChange >= 0 ? 'trending-up' : 'trending-down',
    },
    // 2. Risk alert
    {
      id: `${regionId}-risk`,
      type: 'risk',
      severity: riskSeverity,
      title: templates.risk,
      description: `Alert frequency has ${alertChange >= 0 ? 'increased' : 'decreased'} by ${Math.abs(parseFloat(alertChange.toFixed(1)))}%. Current detection confidence at ${(avgConfSecond * 100).toFixed(0)}%.`,
      reasoning: riskReasoning,
      recommendation: riskRecommendation,
      confidence: riskConfidence,
      percentChange: parseFloat(alertChange.toFixed(1)),
      iconHint: 'alert-triangle',
    },
    // 3. Pattern detection
    {
      id: `${regionId}-pattern`,
      type: 'pattern',
      severity: 'informational',
      title: templates.pattern,
      description: `AI model detected this pattern with ${(avgConfSecond * 100).toFixed(0)}% confidence across ${data.length} observation days. Sustained monitoring recommended.`,
      reasoning: patternReasoning,
      recommendation: patternRecommendation,
      confidence: patternConfidence,
      percentChange: 0,
      iconHint: 'eye',
    },
  ]

  return insights
}

// ─── Reasoning Builders ─────────────────────────────────────────────────────
// Each builder produces a human-readable causal explanation based on the
// environmental factors. Logic is deterministic — same inputs always produce
// the same output.

function buildTrendReasoning(
  factors: EnvironmentalFactors,
  direction: string,
  absChange: number,
  trendType: string,
): string {
  const causes: string[] = []

  // Temperature contribution
  if (factors.tempDelta > 1.5) {
    causes.push(`surface temperature anomaly of +${factors.tempDelta}°C above seasonal baseline accelerating vegetation stress`)
  } else if (factors.tempDelta > 0.5) {
    causes.push(`moderate warming trend (+${factors.tempDelta}°C) contributing to drier conditions`)
  }

  // Precipitation contribution
  if (factors.precipDelta < -20) {
    causes.push(`severe precipitation deficit (${factors.precipDelta}% below climatological mean) creating extended dry conditions`)
  } else if (factors.precipDelta < -10) {
    causes.push(`below-average rainfall (${factors.precipDelta}%) reducing soil moisture recovery`)
  }

  // Human pressure
  if (factors.humanPressure > 0.7) {
    causes.push(factors.drivers.trend[1])
  } else if (factors.humanPressure > 0.4) {
    causes.push('moderate human activity patterns detected in buffer zones')
  }

  // Primary driver
  if (causes.length === 0) {
    causes.push(factors.drivers.trend[0])
  }

  return `${trendType} ${direction} by ${absChange}% — driven by ${causes.join(', and ')}.`
}

function buildRiskReasoning(
  factors: EnvironmentalFactors,
  avgAlertRate: number,
  alertChange: number,
): string {
  const indicators: string[] = []

  // Vegetation health
  if (factors.ndviIndex < 0.4) {
    indicators.push(`critically low vegetation health index (NDVI: ${factors.ndviIndex.toFixed(2)}) indicating severe canopy loss`)
  } else if (factors.ndviIndex < 0.6) {
    indicators.push(`declining vegetation index (NDVI: ${factors.ndviIndex.toFixed(2)}) suggesting progressive canopy degradation`)
  }

  // Soil moisture
  if (factors.soilMoisture < 0.25) {
    indicators.push(`soil moisture at ${(factors.soilMoisture * 100).toFixed(0)}% — critically below safe thresholds`)
  } else if (factors.soilMoisture < 0.4) {
    indicators.push(`reduced soil moisture (${(factors.soilMoisture * 100).toFixed(0)}%) increasing combustibility`)
  }

  // Temperature
  if (factors.tempDelta > 1.0) {
    indicators.push(factors.drivers.risk[1])
  }

  // Alert trend context
  if (alertChange > 20) {
    indicators.push(`alert frequency surge of ${Math.abs(parseFloat(alertChange.toFixed(1)))}% signals escalating conditions`)
  }

  // Always include primary risk driver
  if (indicators.length === 0) {
    indicators.push(factors.drivers.risk[0])
  }

  return `Risk assessment based on: ${indicators.join('; ')}.`
}

function buildPatternReasoning(
  factors: EnvironmentalFactors,
  confidence: number,
  observationDays: number,
): string {
  const methods: string[] = []

  // Primary detection method
  methods.push(factors.drivers.pattern[0])

  // Supporting evidence
  methods.push(factors.drivers.pattern[1])

  // Confidence context
  const confPct = (confidence * 100).toFixed(0)
  const confLevel = confidence > 0.85 ? 'high' : confidence > 0.75 ? 'moderate' : 'preliminary'

  return `Pattern identified through ${methods[0]}, corroborated by ${methods[1]}. Classification confidence: ${confLevel} (${confPct}%) based on ${observationDays}-day temporal analysis.`
}

// ─── Recommendation Builder ─────────────────────────────────────────────────
// Maps insight type + severity to region-specific actionable recommendations.
// Severity 'informational' maps to the 'low' tier.

function buildRecommendation(
  factors: EnvironmentalFactors,
  type: 'trend' | 'risk',
  severity: InsightSeverity,
): string {
  const tierMap: Record<InsightSeverity, 'high' | 'moderate' | 'low'> = {
    high: 'high',
    moderate: 'moderate',
    informational: 'low',
  }
  const tier = tierMap[severity]
  return factors.recommendations[type][tier]
}

// ─── Confidence Score ───────────────────────────────────────────────────────
// Deterministic confidence score (0-100) blending:
//   - Model detection confidence (40% weight)
//   - Observation density (30% weight) — more days = higher confidence
//   - Signal clarity (30% weight) — stronger change signal = higher confidence

function computeConfidence(
  modelConfidence: number,    // 0-1 from avg_confidence
  observationDays: number,    // count of data points
  signalStrength: number,     // abs % change — higher = clearer signal
): number {
  // Model confidence component (0-40)
  const modelScore = modelConfidence * 40

  // Observation density component (0-30)
  // 30 days = full score, scales linearly
  const densityScore = Math.min(observationDays / 30, 1) * 30

  // Signal clarity component (0-30)
  // 20%+ change = full clarity, diminishing returns below
  const clarityScore = Math.min(signalStrength / 20, 1) * 30

  const raw = modelScore + densityScore + clarityScore
  // Clamp to 55-97 range for realism (never 100%, never below 55%)
  return Math.round(Math.min(97, Math.max(55, raw)))
}

export function getRecentAlerts(regionId: string): MockAlert[] {
  const alertsByRegion: Record<string, MockAlert[]> = {
    'region-1': [
      {
        id: 'a1',
        type: 'deforestation',
        severity: 'critical',
        title: 'Large-scale deforestation detected',
        description: '22.1 km² cleared in Northern Amazon corridor. Confidence: 94%.',
        timestamp: '2024-01-28T14:32:00Z',
        region: 'region-1',
        coordinates: [-64.2, -1.8],
      },
      {
        id: 'a2',
        type: 'wildfire',
        severity: 'warning',
        title: 'Active burn scar expanding',
        description: 'Wildfire burn area expanded 8.4 km² in 24h near Rio Negro.',
        timestamp: '2024-01-27T09:15:00Z',
        region: 'region-1',
        coordinates: [-66.1, -3.2],
      },
      {
        id: 'a3',
        type: 'deforestation',
        severity: 'warning',
        title: 'New clearing activity',
        description: 'Incremental clearing detected along BR-319 highway.',
        timestamp: '2024-01-25T18:45:00Z',
        region: 'region-1',
        coordinates: [-63.5, -4.1],
      },
    ],
    'region-2': [
      {
        id: 'b1',
        type: 'deforestation',
        severity: 'critical',
        title: 'Mining-related deforestation',
        description: 'Artisanal mining expanding into protected forest zone.',
        timestamp: '2024-01-29T11:20:00Z',
        region: 'region-2',
        coordinates: [22.4, 1.2],
      },
      {
        id: 'b2',
        type: 'water',
        severity: 'info',
        title: 'River course shift detected',
        description: 'Congo River tributary shifted 500m due to sediment buildup.',
        timestamp: '2024-01-26T07:30:00Z',
        region: 'region-2',
        coordinates: [24.8, -0.5],
      },
    ],
    'region-3': [
      {
        id: 'c1',
        type: 'deforestation',
        severity: 'critical',
        title: 'Palm oil plantation expansion',
        description: '15.3 km² primary forest converted to plantation.',
        timestamp: '2024-01-30T06:45:00Z',
        region: 'region-3',
        coordinates: [112.5, 2.1],
      },
      {
        id: 'c2',
        type: 'wildfire',
        severity: 'critical',
        title: 'Peatland fire detected',
        description: 'Underground peat fire detected across 4.2 km² area.',
        timestamp: '2024-01-28T15:00:00Z',
        region: 'region-3',
        coordinates: [110.8, 0.3],
      },
    ],
    'region-4': [
      {
        id: 'd1',
        type: 'urban',
        severity: 'info',
        title: 'Desertification advance',
        description: 'Desert boundary moved 1.2 km south over monitoring period.',
        timestamp: '2024-01-27T12:00:00Z',
        region: 'region-4',
        coordinates: [2.5, 14.3],
      },
    ],
    'region-5': [
      {
        id: 'e1',
        type: 'deforestation',
        severity: 'critical',
        title: 'Agricultural conversion surge',
        description: '28.7 km² Cerrado savanna converted to soybean fields.',
        timestamp: '2024-01-29T08:30:00Z',
        region: 'region-5',
        coordinates: [-46.2, -14.8],
      },
      {
        id: 'e2',
        type: 'wildfire',
        severity: 'warning',
        title: 'Dry season fire risk elevated',
        description: 'NDVI decline indicates drought stress across 150 km² zone.',
        timestamp: '2024-01-26T16:20:00Z',
        region: 'region-5',
        coordinates: [-49.1, -11.5],
      },
    ],
  }

  return alertsByRegion[regionId] || []
}
