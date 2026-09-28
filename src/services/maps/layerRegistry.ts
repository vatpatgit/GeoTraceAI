/**
 * Central Layer Registry for TerraTrack.
 * All map layers are registered here. Future layers only need to be added to this registry.
 * No layer should be hardcoded inside BaseMap or any component.
 */

import type { LayerDefinition, LayerCategory } from './layerTypes'

/** Complete registry of all available map layers */
export const LAYER_REGISTRY: LayerDefinition[] = [
  // ─── Base Layers ──────────────────────────────────────────────────────
  {
    id: 'satellite',
    name: 'Satellite Imagery',
    category: 'base',
    icon: 'Satellite',
    enabled: true,
    defaultVisible: true,
    defaultOpacity: 1,
    description: 'Sentinel-2 imagery for the selected region and date (via backend)',
  },

  // ─── Monitoring Layers ────────────────────────────────────────────────
  {
    id: 'change-detection',
    name: 'Change Detection',
    category: 'monitoring',
    icon: 'Layers',
    enabled: true,
    defaultVisible: true,
    defaultOpacity: 0.85,
    description: 'AI detected land and environmental change areas',
  },
  {
    id: 'regions',
    name: 'Monitoring Regions',
    category: 'monitoring',
    icon: 'Map',
    enabled: true,
    defaultVisible: true,
    defaultOpacity: 1,
    description: 'GeoJSON region boundaries and selection',
  },
  {
    id: 'region-labels',
    name: 'Region Labels',
    category: 'monitoring',
    icon: 'Type',
    enabled: true,
    defaultVisible: true,
    defaultOpacity: 1,
    description: 'Region name labels on the map',
  },
  {
    id: 'alert-markers',
    name: 'Alert Markers',
    category: 'monitoring',
    icon: 'AlertTriangle',
    enabled: true,
    defaultVisible: true,
    defaultOpacity: 1,
    description: 'Active alert markers with severity indicators',
  },

  // ─── Environmental Layers (Placeholders) ──────────────────────────────
  {
    id: 'ndvi',
    name: 'NDVI',
    category: 'environmental',
    icon: 'Leaf',
    enabled: false,
    defaultVisible: false,
    defaultOpacity: 0.7,
    description: 'Normalized Difference Vegetation Index',
  },
  {
    id: 'temperature',
    name: 'Temperature',
    category: 'environmental',
    icon: 'Thermometer',
    enabled: false,
    defaultVisible: false,
    defaultOpacity: 0.7,
    description: 'Surface temperature anomaly map',
  },
  {
    id: 'rainfall',
    name: 'Rainfall',
    category: 'environmental',
    icon: 'CloudRain',
    enabled: false,
    defaultVisible: false,
    defaultOpacity: 0.7,
    description: 'Precipitation data overlay',
  },
  {
    id: 'soil-moisture',
    name: 'Soil Moisture',
    category: 'environmental',
    icon: 'Droplets',
    enabled: false,
    defaultVisible: false,
    defaultOpacity: 0.7,
    description: 'Soil moisture content analysis',
  },
  {
    id: 'air-quality',
    name: 'Air Quality',
    category: 'environmental',
    icon: 'Wind',
    enabled: false,
    defaultVisible: false,
    defaultOpacity: 0.7,
    description: 'Air quality index monitoring',
  },

  // ─── Risk Assessment Layers (Placeholders) ────────────────────────────
  {
    id: 'wildfire',
    name: 'Wildfire',
    category: 'risk',
    icon: 'Flame',
    enabled: false,
    defaultVisible: false,
    defaultOpacity: 0.7,
    description: 'Active wildfire detection and risk zones',
  },
  {
    id: 'flood-risk',
    name: 'Flood Risk',
    category: 'risk',
    icon: 'Waves',
    enabled: false,
    defaultVisible: false,
    defaultOpacity: 0.7,
    description: 'Flood risk assessment overlay',
  },
  {
    id: 'deforestation',
    name: 'Deforestation',
    category: 'risk',
    icon: 'TreePine',
    enabled: false,
    defaultVisible: false,
    defaultOpacity: 0.7,
    description: 'Deforestation detection and tracking',
  },
]

/** Get all layers grouped by category */
export function getLayersByCategory(): Record<LayerCategory, LayerDefinition[]> {
  const grouped: Record<LayerCategory, LayerDefinition[]> = {
    base: [],
    monitoring: [],
    environmental: [],
    risk: [],
  }

  LAYER_REGISTRY.forEach((layer) => {
    grouped[layer.category].push(layer)
  })

  return grouped
}

/** Get only enabled (non-placeholder) layer IDs */
export function getActiveLayerIds(): string[] {
  return LAYER_REGISTRY.filter((l) => l.enabled).map((l) => l.id)
}

/** Get a single layer definition by ID */
export function getLayerById(layerId: string): LayerDefinition | undefined {
  return LAYER_REGISTRY.find((l) => l.id === layerId)
}
