/**
 * Layer Manager — pure functions for managing layer visibility state.
 * Works with the Zustand store shape without side effects.
 * Provides the bridge between registry definitions and store state.
 */

import type { LayerVisibilityState } from './layerTypes'
import { LAYER_REGISTRY } from './layerRegistry'

/**
 * Generate default layer visibility state from the registry.
 * Only enabled layers get their default visibility; disabled layers are off.
 */
export function getDefaultLayerVisibility(): LayerVisibilityState {
  const state: LayerVisibilityState = {}

  LAYER_REGISTRY.forEach((layer) => {
    state[layer.id] = {
      visible: layer.enabled ? layer.defaultVisible : false,
      opacity: layer.defaultOpacity,
    }
  })

  return state
}

/**
 * Toggle a layer's visibility. Returns a new state object.
 * Only enabled layers can be toggled.
 */
export function toggleLayerVisibility(
  currentState: LayerVisibilityState,
  layerId: string,
): LayerVisibilityState {
  const layer = LAYER_REGISTRY.find((l) => l.id === layerId)
  if (!layer || !layer.enabled) return currentState

  const current = currentState[layerId]
  if (!current) return currentState

  return {
    ...currentState,
    [layerId]: {
      ...current,
      visible: !current.visible,
    },
  }
}

/**
 * Set a layer's opacity. Returns a new state object.
 * Opacity is clamped to 0-1 range.
 */
export function setLayerOpacity(
  currentState: LayerVisibilityState,
  layerId: string,
  opacity: number,
): LayerVisibilityState {
  const current = currentState[layerId]
  if (!current) return currentState

  return {
    ...currentState,
    [layerId]: {
      ...current,
      opacity: Math.max(0, Math.min(1, opacity)),
    },
  }
}

/**
 * Check if a specific layer is currently visible.
 */
export function isLayerVisible(
  state: LayerVisibilityState,
  layerId: string,
): boolean {
  return state[layerId]?.visible ?? false
}

/**
 * Get a layer's current opacity.
 */
export function getLayerOpacity(
  state: LayerVisibilityState,
  layerId: string,
): number {
  return state[layerId]?.opacity ?? 1
}
