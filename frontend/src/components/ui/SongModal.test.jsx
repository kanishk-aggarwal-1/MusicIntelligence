import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { PlayerProvider } from '../../contexts/PlayerContext'
import SongModal from './SongModal'

describe('SongModal accessibility', () => {
  it('is labelled, receives focus, and closes with Escape', () => {
    const onClose = vi.fn()
    render(
      <PlayerProvider>
        <SongModal
          song={{ id: 1, title: 'Accessible Song', artist: 'Test Artist', enrichment_status: 'complete' }}
          onClose={onClose}
        />
      </PlayerProvider>,
    )

    const dialog = screen.getByRole('dialog', { name: 'Accessible Song' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveFocus()
    expect(screen.getByRole('button', { name: /close song details/i })).toBeInTheDocument()

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
