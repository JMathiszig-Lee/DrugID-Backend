const START_KEY_PREFIX = 'ampoule-study-trial-start:'

export type TrialStorageKey = string | number

function keyFor(storageKey: TrialStorageKey): string {
  return `${START_KEY_PREFIX}${storageKey}`
}

export function getOrCreateTrialStart(
  storageKey: TrialStorageKey,
  now = Date.now(),
  storage = window.localStorage,
): number {
  try {
    const stored = Number(storage.getItem(keyFor(storageKey)))
    if (Number.isFinite(stored) && stored > 0 && stored <= now) return stored
    storage.setItem(keyFor(storageKey), String(now))
  } catch {
    // Continue with an in-memory start time if storage is unavailable.
  }
  return now
}

export function clearTrialStart(
  storageKey: TrialStorageKey,
  storage = window.localStorage,
): void {
  try {
    storage.removeItem(keyFor(storageKey))
  } catch {
    // Storage is optional.
  }
}
