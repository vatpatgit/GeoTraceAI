/**
 * Layer type definitions for the map service layer.
 * Re-exports from @/types/layers for convenience.
 */

export type { LayerCategory, LayerDefinition, LayerVisibilityState } from '@/types/layers'
import type { LayerCategory } from '@/types/layers'

/** Category display metadata for the Layer Manager UI */
export interface LayerCategoryMeta {
  id: LayerCategory
  label: string
  description: string
}

export const LAYER_CATEGORIES: LayerCategoryMeta[] = [
  { id: 'base', label: 'Base Layers', description: 'Fundamental map imagery and data' },
  { id: 'monitoring', label: 'Monitoring', description: 'Active monitoring overlays' },
  { id: 'environmental', label: 'Environmental', description: 'Environmental data layers' },
  { id: 'risk', label: 'Risk Assessment', description: 'Risk analysis overlays' },
]
