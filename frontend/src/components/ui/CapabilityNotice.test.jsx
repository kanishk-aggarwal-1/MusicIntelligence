import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import CapabilityNotice from './CapabilityNotice'

describe('CapabilityNotice', () => {
  it('explains that guest-only actions require Spotify', () => {
    render(<CapabilityNotice />)
    expect(screen.getByText(/read-only in the guest demo/i)).toBeInTheDocument()
  })

  it('renders contextual guidance', () => {
    render(<CapabilityNotice>Schedules are disabled in the shared demo.</CapabilityNotice>)
    expect(screen.getByText(/schedules are disabled/i)).toBeInTheDocument()
  })
})
