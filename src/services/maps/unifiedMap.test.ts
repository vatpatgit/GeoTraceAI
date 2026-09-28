import { describe, expect, it } from 'vitest'
import { createUnifiedMapStyle, MAP_LAYERS } from './mapStyle'
import { ESRI_WORLD_IMAGERY, CARTO_DARK_MATTER } from './tileSources'
import { LAYER_REGISTRY } from './layerRegistry'

describe('Unified Map Architecture', () => {
  it('constructs a unified map style containing both satellite and cartographic raster sources', () => {
    const style = createUnifiedMapStyle()
    expect(style.version).toBe(8)
    expect(style.sources['satellite']).toBeDefined()
    expect(style.sources['carto-dark']).toBeDefined()
    expect(style.sources['satellite'].tiles).toEqual(ESRI_WORLD_IMAGERY.tiles)
    expect(style.sources['carto-dark'].tiles).toEqual(CARTO_DARK_MATTER.tiles)

    const layerIds = style.layers.map((l) => l.id)
    expect(layerIds).toContain(MAP_LAYERS.SATELLITE)
    expect(layerIds).toContain(MAP_LAYERS.MAP)
  })

  it('includes change-detection in the layer registry', () => {
    const changeLayer = LAYER_REGISTRY.find((l) => l.id === 'change-detection')
    expect(changeLayer).toBeDefined()
    expect(changeLayer?.enabled).toBe(true)
    expect(changeLayer?.defaultVisible).toBe(true)
    expect(changeLayer?.category).toBe('monitoring')
  })
})
