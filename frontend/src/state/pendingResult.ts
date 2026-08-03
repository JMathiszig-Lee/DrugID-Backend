import type { TrialResultRequest, TrialType } from '../types/study'

const STORAGE_KEY = 'ampoule-study-pending-result'

export interface PendingResult {
  studyId: string | number
  trialId: number
  trialType: TrialType
  result: TrialResultRequest
}

function isPendingResult(value: unknown): value is PendingResult {
  if (!value || typeof value !== 'object') return false

  const candidate = value as Partial<PendingResult>
  const selectedAssetId = candidate.result?.selected_asset_id
  const responseTime = candidate.result?.response_time_ms

  const trialType = candidate.trialType ?? 'study'
  return (
    (typeof candidate.studyId === 'string' || typeof candidate.studyId === 'number') &&
    Number.isInteger(candidate.trialId) &&
    (candidate.trialId ?? 0) > 0 &&
    (trialType === 'tutorial' || trialType === 'study') &&
    (selectedAssetId === null || (Number.isInteger(selectedAssetId) && (selectedAssetId ?? 0) > 0)) &&
    Number.isInteger(responseTime) &&
    (responseTime ?? -1) >= 0
  )
}

export function rememberPendingResult(pending: PendingResult, storage = window.localStorage): void {
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(pending))
  } catch {
    // The in-memory retry path remains available when browser storage is disabled.
  }
}

export function restorePendingResult(
  studyId: string | number,
  storage = window.localStorage,
): PendingResult | null {
  try {
    const raw = storage.getItem(STORAGE_KEY)
    if (!raw) return null

    const pending: unknown = JSON.parse(raw)
    if (!isPendingResult(pending) || String(pending.studyId) !== String(studyId)) {
      storage.removeItem(STORAGE_KEY)
      return null
    }
    return {
      ...pending,
      // Results held by releases before the tutorial flow are real study
      // results. Preserve their retry path while making all new writes explicit.
      trialType: pending.trialType ?? 'study',
    }
  } catch {
    try {
      storage.removeItem(STORAGE_KEY)
    } catch {
      // Storage is unavailable; there is nothing else to clear.
    }
    return null
  }
}

export function clearPendingResult(storage = window.localStorage): void {
  try {
    storage.removeItem(STORAGE_KEY)
  } catch {
    // Storage is optional.
  }
}
