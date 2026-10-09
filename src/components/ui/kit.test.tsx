import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Button, DemoBadge, EmptyBlock, ErrorBlock, IconButton, Segmented, Switch } from './kit'

describe('ui kit', () => {
  it('DemoBadge states plainly that the data is synthetic', () => {
    render(<DemoBadge />)
    expect(screen.getByText(/demo data/i)).toHaveAttribute('title', expect.stringMatching(/synthetic/i))
  })
  it('IconButton always has an accessible name', () => {
    render(<IconButton label="Close panel" onClick={() => {}}>x</IconButton>)
    expect(screen.getByRole('button', { name: 'Close panel' })).toBeInTheDocument()
  })
  it('Switch exposes its state and toggles', async () => {
    const onChange = vi.fn()
    render(<Switch checked={false} onChange={onChange} label="Toggle NDVI" />)
    await userEvent.click(screen.getByRole('switch', { name: 'Toggle NDVI' }))
    expect(onChange).toHaveBeenCalledWith(true)
  })
  it('disabled Switch does not fire', async () => {
    const onChange = vi.fn()
    render(<Switch checked={false} disabled onChange={onChange} label="Toggle" />)
    await userEvent.click(screen.getByRole('switch'))
    expect(onChange).not.toHaveBeenCalled()
  })
  it('Segmented selects options', async () => {
    const onChange = vi.fn()
    render(<Segmented label="View" value="map" onChange={onChange} options={[{ value: 'globe', label: 'Globe' }, { value: 'map', label: 'Map' }]} />)
    expect(screen.getByRole('radio', { name: 'Map' })).toBeChecked()
    await userEvent.click(screen.getByRole('radio', { name: 'Globe' }))
    expect(onChange).toHaveBeenCalledWith('globe')
  })
  it('Button with loading is disabled', () => {
    render(<Button loading>Save</Button>)
    expect(screen.getByRole('button', { name: /save/i })).toBeDisabled()
  })
  it('error and empty states render their messages', async () => {
    const retry = vi.fn()
    render(<><ErrorBlock message="Cannot reach the backend" onRetry={retry} /><EmptyBlock title="Nothing here" hint="Add something" /></>)
    expect(screen.getByRole('alert')).toHaveTextContent('Cannot reach the backend')
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(retry).toHaveBeenCalled()
    expect(screen.getByText('Nothing here')).toBeInTheDocument()
  })
})
