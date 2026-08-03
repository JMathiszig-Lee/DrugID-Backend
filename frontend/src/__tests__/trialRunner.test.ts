import { createApp, h, nextTick, type App } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import TrialRunner from '../components/TrialRunner.vue'
import { getOrCreateTrialStart } from '../lib/trialPersistence'
import type { StudyTrial, TrialSelection } from '../types/study'

const trial: StudyTrial = {
  id: 42,
  trial_type: 'study',
  storage_key: 'study:42',
  sequence: 1,
  sequence_total: 10,
  group_index: 1,
  style_name: 'Industry',
  target_drug: 'adrenaline',
  time_limit_ms: 1_000,
  ampoules: [
    { id: 10, image_url: '/api/study/assets/10/image/' },
    { id: 11, image_url: '/api/study/assets/11/image/' },
  ],
}

let app: App<Element> | null = null
let root: HTMLDivElement
let animationCallbacks: Map<number, FrameRequestCallback>
let animationId: number
let layoutBottom: number
let visibility: DocumentVisibilityState
let performanceNow: number
let wallClockNow: number

function rectangle({
  top = 0,
  right = 1_000,
  bottom = 100,
  left = 0,
}: Partial<DOMRect> = {}): DOMRect {
  return {
    x: left,
    y: top,
    top,
    right,
    bottom,
    left,
    width: right - left,
    height: bottom - top,
    toJSON: () => ({}),
  }
}

function flushAnimationFrame(timestamp = performanceNow): void {
  const pending = [...animationCallbacks.values()]
  animationCallbacks.clear()
  pending.forEach((callback) => callback(timestamp))
}

function mountTrial(onComplete: (selection: TrialSelection) => void = () => undefined): void {
  app = createApp({
    render: () => h(TrialRunner, { trial, onComplete }),
  })
  app.mount(root)
}

async function finishLoadingImages(): Promise<void> {
  root.querySelectorAll('img').forEach((image) => image.dispatchEvent(new Event('load')))
  await nextTick()
  flushAnimationFrame()
  await nextTick()
}

beforeEach(() => {
  vi.useFakeTimers()
  window.localStorage.clear()
  root = document.createElement('div')
  document.body.append(root)
  animationCallbacks = new Map()
  animationId = 0
  layoutBottom = 600
  visibility = 'visible'
  performanceNow = 1_000
  wallClockNow = 10_000

  vi.stubGlobal(
    'requestAnimationFrame',
    vi.fn((callback: FrameRequestCallback) => {
      animationId += 1
      animationCallbacks.set(animationId, callback)
      return animationId
    }),
  )
  vi.stubGlobal(
    'cancelAnimationFrame',
    vi.fn((id: number) => animationCallbacks.delete(id)),
  )
  vi.spyOn(performance, 'now').mockImplementation(() => performanceNow)
  vi.spyOn(Date, 'now').mockImplementation(() => wallClockNow)
  vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => visibility)
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1_024 })
  Object.defineProperty(window, 'innerHeight', { configurable: true, value: 768 })
  Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
    configurable: true,
    value: vi.fn(),
  })
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (
    this: HTMLElement,
  ) {
    if (this.classList.contains('trial-header')) return rectangle({ bottom: 100 })
    if (this.classList.contains('ampoule-grid')) {
      return rectangle({ top: 120, bottom: layoutBottom })
    }
    return rectangle()
  })
})

afterEach(() => {
  app?.unmount()
  app = null
  root.remove()
  window.localStorage.clear()
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('TrialRunner', () => {
  it('waits for an explicit ready action and emits one measured choice', async () => {
    const completions: TrialSelection[] = []
    mountTrial((selection) => completions.push(selection))
    await finishLoadingImages()

    const startButton = root.querySelector<HTMLButtonElement>('.ready-panel button')
    expect(startButton).not.toBeNull()
    expect(root.querySelector('.ampoule-grid')?.classList).toContain('ampoule-grid--concealed')

    startButton?.click()
    startButton?.click()
    expect(animationCallbacks.size).toBe(1)
    flushAnimationFrame()
    await nextTick()

    const choices = root.querySelectorAll<HTMLButtonElement>('.ampoule-option')
    expect(root.querySelector('.ready-panel')).toBeNull()
    expect(choices).toHaveLength(2)
    expect(choices[0]?.disabled).toBe(false)

    performanceNow = 1_275
    choices[0]?.click()
    expect(completions).toEqual([{ selectedAssetId: 10, responseTimeMs: 275 }])
  })

  it('does not arm in a hidden tab or when the complete stimulus is off-screen', async () => {
    mountTrial()
    await finishLoadingImages()

    const startButton = root.querySelector<HTMLButtonElement>('.ready-panel button')
    visibility = 'hidden'
    document.dispatchEvent(new Event('visibilitychange'))
    await nextTick()
    expect(startButton?.disabled).toBe(true)
    expect(root.textContent).toContain('Return to this tab')

    visibility = 'visible'
    document.dispatchEvent(new Event('visibilitychange'))
    layoutBottom = 900
    window.dispatchEvent(new Event('resize'))
    await nextTick()
    expect(startButton?.disabled).toBe(true)
    expect(root.textContent).toContain('More screen space is needed')
  })

  it('reports an image-loading stall without marking the region busy forever', async () => {
    mountTrial()
    await vi.advanceTimersByTimeAsync(15_000)
    await nextTick()

    expect(root.textContent).toContain('took too long to load')
    expect(root.querySelector('.trial')?.getAttribute('aria-busy')).toBe('false')
  })

  it('preserves an elapsed active timer and records a timeout after reload', async () => {
    const completions: TrialSelection[] = []
    getOrCreateTrialStart(trial.storage_key, 10_000)
    wallClockNow = 11_500
    mountTrial((selection) => completions.push(selection))
    await finishLoadingImages()

    root.querySelector<HTMLButtonElement>('.ready-panel button')?.click()
    flushAnimationFrame()
    await nextTick()
    flushAnimationFrame()

    expect(completions).toEqual([{ selectedAssetId: null, responseTimeMs: 1_000 }])
  })

  it('labels a tutorial trial and keeps its timer key separate from study trials', async () => {
    const tutorialTrial: StudyTrial = {
      ...trial,
      id: 7,
      trial_type: 'tutorial',
      storage_key: 'tutorial:3:7',
      sequence: 2,
      sequence_total: 6,
      group_index: null,
      style_name: 'ISO',
    }
    getOrCreateTrialStart('study:7', 9_000)
    app = createApp({
      render: () => h(TrialRunner, { trial: tutorialTrial }),
    })
    app.mount(root)
    await finishLoadingImages()

    expect(root.textContent).toContain('Practice 2 of 6 · ISO')
    expect(root.textContent).toContain('Start practice trial')
    expect(getOrCreateTrialStart('study:7', 10_000)).toBe(9_000)
    expect(getOrCreateTrialStart(tutorialTrial.storage_key, 10_000)).toBe(10_000)
  })
})
