/**
 * Layer system type definitions for TerraTrack GIS Intelligence Layer
 */

export type LayerCategory = 'base' | 'monitoring' | 'environmental' | 'risk'

export interface LayerDefinition {
  /** Unique layer identifier */
  id: string
  /** Display name */
  name: string
  /** Layer category for grouping */
  category: LayerCategory
  /** Lucide icon name */
  icon: string
  /** Whether this layer is currently implemented (vs placeholder) */
  enabled: boolean
  /** Default visibility */
  defaultVisible: boolean
  /** Default opacity (0-1) */
  defaultOpacity: number
  /** Short description */
  description: string
}

export interface LayerVisibilityState {
  [layerId: string]: {
    visible: boolean
    opacity: number
  }
}
