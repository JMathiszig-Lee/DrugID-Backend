import { createApp, defineComponent, h, nextTick, type App } from 'vue'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  getNextTrial,
  getNextTutorialTrial,
  getStudySession,
  logOut,
  submitTrialResult,
  submitTutorialTrialResult,
} from '../api/study'
import { rememberPendingResult } from '../state/pendingResult'
import type { StudySessionStatus, StudyTrial } from '../types/study'
import StudyView from '../views/StudyView.vue'

vi.mock('../api/study', () => ({
  getNextTrial: vi.fn(),
  getNextTutorialTrial: vi.fn(),
  getStudySession: vi.fn(),
  logOut: vi.fn(),
  submitTrialResult: vi.fn(),
  submitTutorialTrialResult: vi.fn(),
}))

vi.mock('../components/TrialRunner.vue', async () => {
  const { defineComponent: define, h: render } = await import('vue')
  return {
    default: define({
      name: 'TrialRunnerStub',
      emits: ['complete'],
      setup(_, { emit }) {
        return () =>
          render(
            'button',
            {
              class: 'trial-runner-stub',
              type: 'button',
              onClick: () => emit('complete', { selectedAssetId: 11, responseTimeMs: 420 }),
            },
            'Complete displayed trial',
          )
      },
    }),
  }
})

const mockedGetSession = vi.mocked(getStudySession)
const mockedGetStudyTrial = vi.mocked(getNextTrial)
const mockedGetTutorialTrial = vi.mocked(getNextTutorialTrial)
const mockedSubmitStudy = vi.mocked(submitTrialResult)
const mockedSubmitTutorial = vi.mocked(submitTutorialTrialResult)
const mockedLogout = vi.mocked(logOut)

let app: App<Element> | null = null
let root: HTMLDivElement

function session(
  phase: StudySessionStatus['phase'],
  tutorial: Partial<StudySessionStatus['tutorial']> = {},
): StudySessionStatus {
  return {
    id: 3,
    phase,
    group_index: phase === 'tutorial' ? null : 1,
    groups_total: 3,
    current_group_name: phase === 'tutorial' ? null : 'Industry',
    completed_trials: 0,
    total_trials: 150,
    completed_in_group: 0,
    trials_per_group: 50,
    choices_per_trial: 8,
    time_limit_ms: 3_000,
    has_active_trial: phase === 'in_progress',
    tutorial: {
      required: 6,
      complete: phase !== 'tutorial',
      completed_trials: 0,
      total_trials: 6,
      has_active_trial: false,
      ...tutorial,
    },
  }
}

function trial(trialType: StudyTrial['trial_type'], sequence: number): StudyTrial {
  return {
    id: trialType === 'tutorial' ? 17 + sequence : 100 + sequence,
    trial_type: trialType,
    storage_key: `${trialType}:3:${sequence}`,
    sequence,
    sequence_total: trialType === 'tutorial' ? 6 : 50,
    group_index: trialType === 'tutorial' ? null : 1,
    style_name: sequence % 2 ? 'ISO' : 'Black and white',
    target_drug: 'adrenaline',
    time_limit_ms: 3_000,
    ampoules: [
      { id: 11, image_url: '/tutorial/11.png' },
      { id: 12, image_url: '/tutorial/12.png' },
    ],
  }
}

async function mountStudyView(): Promise<void> {
  const placeholder = defineComponent({ render: () => h('div') })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'landing', component: placeholder },
      { path: '/register', name: 'register', component: placeholder },
      { path: '/study', name: 'study', component: StudyView },
    ],
  })
  await router.push('/study')
  await router.isReady()
  app = createApp({ render: () => h(RouterView) })
  app.use(router)
  app.mount(root)
  await vi.waitFor(() => expect(mockedGetSession).toHaveBeenCalledOnce())
  await nextTick()
}

function buttonContaining(label: string): HTMLButtonElement {
  const button = [...root.querySelectorAll<HTMLButtonElement>('button')].find((candidate) =>
    candidate.textContent?.includes(label),
  )
  if (!button) throw new Error(`Button containing ${label} was not rendered`)
  return button
}

beforeEach(() => {
  root = document.createElement('div')
  document.body.append(root)
  window.localStorage.clear()
  vi.clearAllMocks()
  mockedLogout.mockResolvedValue()
})

afterEach(() => {
  app?.unmount()
  app = null
  root.remove()
  window.localStorage.clear()
})

describe('StudyView tutorial flow', () => {
  it('requires the mixed-style introduction and pauses for feedback before continuing', async () => {
    const initial = session('tutorial')
    const active = session('tutorial', { has_active_trial: true })
    const afterFirst = session('tutorial', { completed_trials: 1 })
    mockedGetSession.mockResolvedValue(initial)
    mockedGetTutorialTrial
      .mockResolvedValueOnce({ status: active, trial: trial('tutorial', 1) })
      .mockResolvedValueOnce({ status: active, trial: trial('tutorial', 2) })
    mockedSubmitTutorial.mockResolvedValue({
      status: afterFirst,
      feedback: { correct: true, timed_out: false, sequence: 1, total_trials: 6 },
    })

    await mountStudyView()

    expect(root.textContent).toContain('Practice trials mix Industry, ISO and black-and-white')
    expect(root.textContent).toContain('same device and input method')
    expect(root.textContent).toContain('0 of 6 practice trials')
    expect(root.textContent).not.toContain('0 of 150 trials')
    expect(mockedGetStudyTrial).not.toHaveBeenCalled()

    buttonContaining('Begin practice').click()
    await vi.waitFor(() => expect(mockedGetTutorialTrial).toHaveBeenCalledOnce())
    await vi.waitFor(() => expect(root.querySelector('.trial-runner-stub')).not.toBeNull())
    buttonContaining('Complete displayed trial').click()
    await vi.waitFor(() => expect(mockedSubmitTutorial).toHaveBeenCalledOnce())
    await vi.waitFor(() => expect(root.textContent).toContain('Correct'))

    expect(mockedSubmitTutorial).toHaveBeenCalledWith(18, {
      selected_asset_id: 11,
      response_time_ms: 420,
    })
    expect(mockedSubmitStudy).not.toHaveBeenCalled()
    expect(root.textContent).toContain('not included in the study results')
    expect(mockedGetTutorialTrial).toHaveBeenCalledTimes(1)

    buttonContaining('Continue practice').click()
    await vi.waitFor(() => expect(mockedGetTutorialTrial).toHaveBeenCalledTimes(2))
  })

  it('requires both feedback continuation and an explicit real-study start', async () => {
    const beforeFinal = session('tutorial', { completed_trials: 5 })
    const active = session('tutorial', { completed_trials: 5, has_active_trial: true })
    const ready = session('ready', {
      required: 6,
      complete: true,
      completed_trials: 6,
    })
    const inProgress = { ...ready, phase: 'in_progress' as const, has_active_trial: true }
    mockedGetSession.mockResolvedValue(beforeFinal)
    mockedGetTutorialTrial.mockResolvedValue({ status: active, trial: trial('tutorial', 6) })
    mockedSubmitTutorial.mockResolvedValue({
      status: ready,
      feedback: { correct: false, timed_out: false, sequence: 6, total_trials: 6 },
    })
    mockedGetStudyTrial.mockResolvedValue({ status: inProgress, trial: trial('study', 1) })

    await mountStudyView()
    buttonContaining('Continue practice').click()
    await vi.waitFor(() => expect(mockedGetTutorialTrial).toHaveBeenCalledOnce())
    await vi.waitFor(() => expect(root.querySelector('.trial-runner-stub')).not.toBeNull())
    buttonContaining('Complete displayed trial').click()
    await vi.waitFor(() => expect(root.textContent).toContain('Not quite'))

    expect(mockedGetStudyTrial).not.toHaveBeenCalled()
    buttonContaining('Continue to study instructions').click()
    await nextTick()
    expect(root.textContent).toContain('Your study is ready')
    expect(mockedGetStudyTrial).not.toHaveBeenCalled()

    buttonContaining('Begin study').click()
    await vi.waitFor(() => expect(mockedGetStudyTrial).toHaveBeenCalledOnce())
    expect(mockedSubmitStudy).not.toHaveBeenCalled()
  })

  it('retries a pending tutorial submission after refresh through only the tutorial endpoint', async () => {
    const active = session('tutorial', { has_active_trial: true })
    const afterFirst = session('tutorial', { completed_trials: 1 })
    rememberPendingResult({
      studyId: 3,
      trialId: 22,
      trialType: 'tutorial',
      result: { selected_asset_id: null, response_time_ms: 3_000 },
    })
    mockedGetSession.mockResolvedValue(active)
    mockedSubmitTutorial.mockResolvedValue({
      status: afterFirst,
      feedback: { correct: false, timed_out: true, sequence: 1, total_trials: 6 },
    })

    await mountStudyView()
    await vi.waitFor(() => expect(mockedSubmitTutorial).toHaveBeenCalledOnce())

    expect(mockedSubmitTutorial).toHaveBeenCalledWith(22, {
      selected_asset_id: null,
      response_time_ms: 3_000,
    })
    expect(mockedSubmitStudy).not.toHaveBeenCalled()
    expect(mockedGetStudyTrial).not.toHaveBeenCalled()
    expect(root.textContent).toContain('Time ran out')
    expect(window.localStorage.getItem('ampoule-study-pending-result')).toBeNull()
  })
})
