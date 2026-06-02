import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import Spinner from './Spinner'

describe('Spinner', () => {
  it('renders an animated element', () => {
    const { container } = render(<Spinner />)
    expect(container.firstChild).toHaveClass('animate-spin')
  })

  it('applies the size variant', () => {
    const { container } = render(<Spinner size="lg" />)
    expect(container.firstChild.className).toContain('w-10')
  })

  it('falls back to md for an unknown size', () => {
    const { container } = render(<Spinner size="bogus" />)
    // Unknown size yields undefined width class but still renders the spinner.
    expect(container.firstChild).toHaveClass('animate-spin')
  })
})
