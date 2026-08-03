export function normaliseResponseTime(startedAt: number, endedAt: number, limitMs: number): number {
  if (!Number.isFinite(startedAt) || !Number.isFinite(endedAt) || !Number.isFinite(limitMs)) {
    throw new TypeError('Trial timing values must be finite numbers.')
  }

  const safeLimit = Math.max(0, limitMs)
  return Math.round(Math.min(Math.max(endedAt - startedAt, 0), safeLimit))
}

export function remainingTime(startedAt: number, now: number, limitMs: number): number {
  return Math.max(0, limitMs - Math.max(0, now - startedAt))
}
