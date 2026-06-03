import { describe, it, expect } from 'vitest'
import { explanationChips } from './Playlists'

describe('explanationChips', () => {
  it('returns an empty list when there is no breakdown', () => {
    expect(explanationChips(null)).toEqual([])
    expect(explanationChips(undefined)).toEqual([])
  })

  it('formats similarity and familiarity as percentages', () => {
    const chips = explanationChips({ tfidf_similarity: 0.82, familiarity_score: 0.5 })
    expect(chips).toContain('Tag match 82%')
    expect(chips).toContain('Familiarity 50%')
  })

  it('includes co-occurrence only when positive', () => {
    expect(explanationChips({ co_occurrence_boost: 0.1 })).toContain('Often heard together')
    expect(explanationChips({ co_occurrence_boost: 0 })).not.toContain('Often heard together')
  })

  it('pluralizes feedback signals correctly', () => {
    expect(explanationChips({ feedback_events: 1 })).toContain('1 feedback signal')
    expect(explanationChips({ feedback_events: 3 })).toContain('3 feedback signals')
  })
})
