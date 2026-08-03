import { describe, expect, it } from 'vitest'
import { normaliseResponseTime, remainingTime } from '../lib/trialTiming'

describe('normaliseResponseTime', () => {
  it('rounds a valid elapsed reaction time to milliseconds', () => {
    expect(normaliseResponseTime(100, 487.6, 1_000)).toBe(388)
  })

  it('clamps measurements to the trial bounds', () => {
    expect(normaliseResponseTime(100, 90, 1_000)).toBe(0)
    expect(normaliseResponseTime(100, 1_400, 1_000)).toBe(1_000)
  })

  it('rejects non-finite timing values', () => {
    expect(() => normaliseResponseTime(Number.NaN, 100, 1_000)).toThrow(TypeError)
  })
})

describe('remainingTime', () => {
  it('counts down without returning a negative value', () => {
    expect(remainingTime(1_000, 1_250, 2_000)).toBe(1_750)
    expect(remainingTime(1_000, 4_000, 2_000)).toBe(0)
  })
})
