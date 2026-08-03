import { afterEach, describe, expect, it } from 'vitest'
import { clearTrialStart, getOrCreateTrialStart } from '../lib/trialPersistence'
import {
  clearPendingResult,
  rememberPendingResult,
  restorePendingResult,
} from '../state/pendingResult'

afterEach(() => {
  window.localStorage.clear()
})

describe('trial start persistence', () => {
  it('keeps the original timer start across a page reload', () => {
    expect(getOrCreateTrialStart(12, 1_000)).toBe(1_000)
    expect(getOrCreateTrialStart(12, 1_750)).toBe(1_000)
  })

  it('can clear a completed trial start', () => {
    getOrCreateTrialStart(12, 1_000)
    clearTrialStart(12)
    expect(getOrCreateTrialStart(12, 2_000)).toBe(2_000)
  })
})

describe('pending result persistence', () => {
  const pending = {
    studyId: 3,
    trialId: 42,
    trialType: 'tutorial' as const,
    result: { selected_asset_id: 9, response_time_ms: 731 },
  }

  it('restores an interrupted submission for the same study', () => {
    rememberPendingResult(pending)
    expect(restorePendingResult(3)).toEqual(pending)
  })

  it('discards a pending submission when another participant signs in', () => {
    rememberPendingResult(pending)
    expect(restorePendingResult(4)).toBeNull()
  })

  it('clears a confirmed submission', () => {
    rememberPendingResult(pending)
    clearPendingResult()
    expect(restorePendingResult(3)).toBeNull()
  })

  it('restores a legacy undiscriminated result as a study result', () => {
    window.localStorage.setItem(
      'ampoule-study-pending-result',
      JSON.stringify({
        studyId: 3,
        trialId: 42,
        result: { selected_asset_id: 9, response_time_ms: 731 },
      }),
    )

    expect(restorePendingResult(3)).toEqual({
      studyId: 3,
      trialId: 42,
      trialType: 'study',
      result: { selected_asset_id: 9, response_time_ms: 731 },
    })
  })
})
