import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import type { LayerInfo } from '@/lib/api'
import { useAppStore } from '@/store/useAppStore'
import LayerPanel from './LayerPanel'

const layer = (over: Partial<LayerInfo>): LayerInfo => ({
  id: 'ndvi', name: 'NDVI (MODIS)', group: 'environmental', provider: 'NASA GIBS', data_type: 'observed', render_type: 'wmts', crs: 'EPSG:3857',
  tile_url: 'https://example.test/{z}/{y}/{x}.png', attribution: 'NASA', limitations: ['Coarse 250 m resolution'], legend: { kind: 'gradient', unit: 'NDVI', stops: [{ value: '0', color: '#000' }, { value: '1', color: '#0f0' }] },
  temporal: { kind: 'daily', default_time: '2026-09-14' }, default_visible: false, default_opacity: 0.7, availability: 'available', availability_detail: null,
  last_checked_at: null, last_updated_at: null, ...over,
})

beforeEach(() => {
  const st = useAppStore.getState()
  useAppStore.setState({
    analyses: [], activeAnalysisId: null,
    layerCatalog: [],
    layerState: { ...st.layerState },
  })
  st.setLayerCatalog([
    layer({}),
    layer({ id: 'rainfall', name: 'Rainfall (IMERG)', availability: 'unavailable', availability_detail: 'provider returned 404' }),
    layer({ id: 'wildfire', name: 'Active fire hotspots', group: 'risk', limitations: ['Hotspot detections are not a risk forecast'] }),
    layer({ id: 'ndvi-after', name: 'NDVI after', render_type: 'analysis_raster', availability: 'requires_analysis', tile_url: null }),
  ])
})

describe('LayerPanel', () => {
  it('lists change, environmental and risk layers', () => {
    render(<LayerPanel />)
    expect(screen.getByRole('switch', { name: 'Toggle Change polygons' })).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'Toggle NDVI (MODIS)' })).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'Toggle Active fire hotspots' })).toBeInTheDocument()
  })

  it('toggling a layer updates shared state and reveals opacity + legend', async () => {
    render(<LayerPanel />)
    await userEvent.click(screen.getByRole('switch', { name: 'Toggle NDVI (MODIS)' }))
    expect(useAppStore.getState().layerState['ndvi'].visible).toBe(true)
    expect(screen.getByRole('slider', { name: 'NDVI (MODIS) opacity' })).toBeInTheDocument()
  })

  it('unavailable layers are disabled and say why', async () => {
    render(<LayerPanel />)
    const sw = screen.getByRole('switch', { name: 'Toggle Rainfall (IMERG)' })
    expect(sw).toBeDisabled()
    expect(screen.getByText('unavailable')).toBeInTheDocument()
    await userEvent.click(sw)
    expect(useAppStore.getState().layerState['rainfall']?.visible).toBeFalsy()
  })

  it('analysis-derived layers need an analysis with red+NIR bands', () => {
    render(<LayerPanel />)
    expect(screen.getByRole('switch', { name: 'Toggle NDVI after' })).toBeDisabled()
    expect(screen.getByText('needs analysis')).toBeInTheDocument()
  })

  it('imagery layers are explained when no analysis is selected', () => {
    render(<LayerPanel />)
    expect(screen.getAllByText('Select a completed analysis').length).toBeGreaterThan(0)
  })
})
