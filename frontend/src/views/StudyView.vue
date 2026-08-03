<script setup lang="ts">
import { computed, onMounted, ref, shallowRef } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { ApiError } from '../api/client'
import {
  getNextTrial as getNextStudyTrial,
  getNextTutorialTrial,
  getStudySession,
  logOut,
  submitTrialResult,
  submitTutorialTrialResult,
} from '../api/study'
import BaseAlert from '../components/BaseAlert.vue'
import StudyProgress from '../components/StudyProgress.vue'
import TrialRunner from '../components/TrialRunner.vue'
import TutorialProgress from '../components/TutorialProgress.vue'
import {
  clearPendingResult,
  rememberPendingResult,
  restorePendingResult,
  type PendingResult,
} from '../state/pendingResult'
import { clearRegistrationResponse } from '../state/registration'
import type {
  StudySessionStatus,
  StudyTrial,
  TutorialFeedback,
  TrialSelection,
} from '../types/study'

const router = useRouter()
const status = shallowRef<StudySessionStatus | null>(null)
const activeTrial = shallowRef<StudyTrial | null>(null)
const pendingSubmission = shallowRef<PendingResult | null>(null)
const tutorialFeedback = shallowRef<TutorialFeedback | null>(null)

const loadingSession = ref(true)
const loadingTrial = ref(false)
const submittingResult = ref(false)
const reconcilingResult = ref(false)
const loggingOut = ref(false)
const unauthorised = ref(false)
const sessionError = ref('')
const trialError = ref('')
const submissionError = ref('')

const showingTutorial = computed(
  () =>
    status.value?.phase === 'tutorial' ||
    activeTrial.value?.trial_type === 'tutorial' ||
    pendingSubmission.value?.trialType === 'tutorial' ||
    tutorialFeedback.value !== null,
)

const timeLimitSeconds = computed(() => {
  if (!status.value) return '—'
  return (status.value.time_limit_ms / 1000).toLocaleString(undefined, {
    maximumFractionDigits: 1,
  })
})

const phaseHeading = computed(() => {
  switch (status.value?.phase) {
    case 'tutorial':
      if (status.value.tutorial.has_active_trial) return 'Resume your practice trial'
      return status.value.tutorial.completed_trials > 0
        ? 'Continue your practice'
        : 'Practise before the study begins'
    case 'ready':
      return 'Your study is ready'
    case 'between_groups':
      return 'Group complete — take a short break'
    case 'completed':
      return 'Thank you — your study is complete'
    default:
      return status.value?.has_active_trial ? 'Resume your current trial' : 'Continue your study'
  }
})

const phaseDescription = computed(() => {
  switch (status.value?.phase) {
    case 'tutorial':
      return status.value.tutorial.completed_trials > 0
        ? 'Continue when you are ready. Practice responses are kept separate from the study results.'
        : 'Complete the short practice first. It uses all three presentation styles and the same timing as the real study.'
    case 'ready':
      return 'Begin when you are settled and ready to concentrate. The first target appears only after every image has loaded.'
    case 'between_groups':
      return 'Your responses are saved. Continue when you are ready for the next presentation style.'
    case 'completed':
      return 'Every response from all presentation groups has been saved.'
    default:
      return status.value?.has_active_trial
        ? 'The server has kept your active trial. Resume when you are ready.'
        : 'Continue with the next trial when you are ready.'
  }
})

const actionLabel = computed(() => {
  if (loadingTrial.value) return 'Preparing trial…'
  switch (status.value?.phase) {
    case 'tutorial':
      if (status.value.tutorial.has_active_trial) return 'Resume practice trial'
      return status.value.tutorial.completed_trials > 0 ? 'Continue practice' : 'Begin practice'
    case 'ready':
      return 'Begin study'
    case 'between_groups':
      return 'Start next group'
    default:
      return status.value?.has_active_trial ? 'Resume trial' : 'Continue'
  }
})

function showError(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback
}

function handleUnauthorised(error: unknown): boolean {
  if (error instanceof ApiError && error.status === 401) {
    unauthorised.value = true
    activeTrial.value = null
    pendingSubmission.value = null
    tutorialFeedback.value = null
    return true
  }
  return false
}

async function loadSession(): Promise<void> {
  loadingSession.value = true
  sessionError.value = ''
  unauthorised.value = false
  let restoredPendingResult = false

  try {
    status.value = await getStudySession()
    if (!pendingSubmission.value) {
      pendingSubmission.value = restorePendingResult(status.value.id)
      restoredPendingResult = pendingSubmission.value !== null
    }
  } catch (error) {
    if (!handleUnauthorised(error)) {
      sessionError.value = showError(error, 'The study session could not be loaded. Please try again.')
    }
  } finally {
    loadingSession.value = false
  }

  if (restoredPendingResult && !unauthorised.value) await submitPendingResult()
}

async function loadNextTrial(): Promise<void> {
  if (
    loadingTrial.value ||
    submittingResult.value ||
    pendingSubmission.value ||
    activeTrial.value ||
    tutorialFeedback.value ||
    !status.value
  ) {
    return
  }

  loadingTrial.value = true
  trialError.value = ''

  try {
    const tutorialRequest = status.value.phase === 'tutorial'
    const response = tutorialRequest
      ? await getNextTutorialTrial()
      : await getNextStudyTrial()
    status.value = response.status

    if (response.trial) {
      const expectedType = tutorialRequest ? 'tutorial' : 'study'
      if (response.trial.trial_type !== expectedType) {
        throw new Error(`The server returned a ${response.trial.trial_type} trial unexpectedly.`)
      }
      activeTrial.value = response.trial
    } else if (response.status.phase === 'in_progress' || response.status.phase === 'tutorial') {
      trialError.value = 'The server did not return the next trial. Refresh your study status and retry.'
    }
  } catch (error) {
    if (!handleUnauthorised(error)) {
      trialError.value = showError(error, 'The next trial could not be loaded. Please try again.')
    }
  } finally {
    loadingTrial.value = false
  }
}

async function submitPendingResult(): Promise<void> {
  if (!pendingSubmission.value || submittingResult.value) return

  const submission = pendingSubmission.value
  submittingResult.value = true
  submissionError.value = ''
  let continueImmediately = false

  try {
    if (submission.trialType === 'tutorial') {
      const response = await submitTutorialTrialResult(submission.trialId, submission.result)
      status.value = response.status
      tutorialFeedback.value = response.feedback
    } else {
      const response = await submitTrialResult(submission.trialId, submission.result)
      status.value = response.status
      continueImmediately = response.status.phase === 'in_progress'
    }
    pendingSubmission.value = null
    clearPendingResult()
  } catch (error) {
    if (!handleUnauthorised(error)) {
      submissionError.value = showError(
        error,
        submission.trialType === 'tutorial'
          ? 'Your practice response could not be confirmed. It is safe to retry this same response.'
          : 'Your result could not be confirmed. It is safe to retry this same result.',
      )
    }
  } finally {
    submittingResult.value = false
  }

  if (continueImmediately && !unauthorised.value) await loadNextTrial()
}

function handleTrialComplete(selection: TrialSelection): void {
  if (!activeTrial.value || !status.value || pendingSubmission.value || submittingResult.value) return

  pendingSubmission.value = {
    studyId: status.value.id,
    trialId: activeTrial.value.id,
    trialType: activeTrial.value.trial_type,
    result: {
      selected_asset_id: selection.selectedAssetId,
      response_time_ms: selection.responseTimeMs,
    },
  }
  rememberPendingResult(pendingSubmission.value)
  activeTrial.value = null
  void submitPendingResult()
}

async function refreshAfterSubmissionError(): Promise<void> {
  if (
    !pendingSubmission.value ||
    pendingSubmission.value.trialType !== 'study' ||
    reconcilingResult.value ||
    !status.value
  ) {
    return
  }

  reconcilingResult.value = true
  const previouslyCompleted = status.value.completed_trials
  let continueImmediately = false

  try {
    const latestStatus = await getStudySession()
    status.value = latestStatus

    if (latestStatus.completed_trials > previouslyCompleted || !latestStatus.has_active_trial) {
      pendingSubmission.value = null
      clearPendingResult()
      submissionError.value = ''
      continueImmediately = latestStatus.phase === 'in_progress'
    } else {
      submissionError.value = 'The server is still waiting for this result. Retry saving it.'
    }
  } catch (error) {
    if (!handleUnauthorised(error)) {
      submissionError.value = showError(error, 'The server status could not be checked. Retry saving the result.')
    }
  } finally {
    reconcilingResult.value = false
  }

  if (continueImmediately && !unauthorised.value) await loadNextTrial()
}

async function continueAfterTutorialFeedback(): Promise<void> {
  if (!tutorialFeedback.value || !status.value) return

  tutorialFeedback.value = null
  if (status.value.phase === 'tutorial') await loadNextTrial()
}

async function signOut(): Promise<void> {
  if (loggingOut.value) return

  loggingOut.value = true
  sessionError.value = ''
  try {
    await logOut()
    clearRegistrationResponse()
    clearPendingResult()
    await router.replace({ name: 'landing' })
  } catch (error) {
    sessionError.value = showError(error, 'Sign out failed. Please try again.')
  } finally {
    loggingOut.value = false
  }
}

onMounted(loadSession)

onBeforeRouteLeave(() => {
  if (!activeTrial.value) return true
  return window.confirm(
    activeTrial.value.trial_type === 'tutorial'
      ? 'Leave this page? The timed practice trial will continue, so staying here is recommended.'
      : 'Leave this page? The timed trial will continue, so staying here is recommended.',
  )
})
</script>

<template>
  <div class="page study-page">
    <section v-if="loadingSession" class="message-card study-message" aria-busy="true">
      <span class="spinner spinner--large" aria-hidden="true"></span>
      <span class="eyebrow">Study session</span>
      <h1>Loading your progress</h1>
      <p class="lede" role="status">Checking the latest state saved by the research server…</p>
    </section>

    <section v-else-if="unauthorised" class="message-card study-message">
      <span class="eyebrow">Session expired</span>
      <h1>Use a new study link to continue</h1>
      <BaseAlert tone="error" title="You are no longer signed in">
        <p>Your saved progress remains on the server, but this browser session has expired.</p>
      </BaseAlert>
      <RouterLink class="button button--primary" :to="{ name: 'register' }">Request a new link</RouterLink>
    </section>

    <section v-else-if="sessionError && !status" class="message-card study-message">
      <span class="eyebrow">Connection problem</span>
      <h1>We could not load your study</h1>
      <BaseAlert tone="error"><p>{{ sessionError }}</p></BaseAlert>
      <button class="button button--primary" type="button" @click="loadSession">Try again</button>
    </section>

    <div v-else-if="status" class="study-shell">
      <TutorialProgress v-if="showingTutorial" :tutorial="status.tutorial" />
      <StudyProgress v-else :status="status" />

      <TrialRunner
        v-if="activeTrial"
        :key="activeTrial.storage_key"
        :trial="activeTrial"
        @complete="handleTrialComplete"
      />

      <section v-else-if="pendingSubmission" class="message-card study-message">
        <template v-if="submittingResult">
          <span class="spinner spinner--large" aria-hidden="true"></span>
          <span class="eyebrow">
            {{ pendingSubmission.trialType === 'tutorial' ? 'Checking practice' : 'Saving response' }}
          </span>
          <h1>
            {{ pendingSubmission.trialType === 'tutorial' ? 'Checking your answer' : 'Your result is being recorded' }}
          </h1>
          <p class="lede" role="status">Keep this page open for a moment.</p>
        </template>

        <template v-else>
          <span class="eyebrow">
            {{ pendingSubmission.trialType === 'tutorial' ? 'Practice not confirmed' : 'Response not confirmed' }}
          </span>
          <h1>
            {{ pendingSubmission.trialType === 'tutorial' ? 'Your practice answer is held safely' : 'Your result is held safely in this page' }}
          </h1>
          <BaseAlert tone="error" title="Saving was interrupted">
            <p>{{ submissionError }}</p>
          </BaseAlert>
          <p>
            Retry sends the same {{ pendingSubmission.trialType === 'tutorial' ? 'practice answer' : 'trial result' }};
            it does not start a second timed attempt.
          </p>
          <div class="button-row button-row--centre">
            <button class="button button--primary" type="button" @click="submitPendingResult">
              {{ pendingSubmission.trialType === 'tutorial' ? 'Retry checking answer' : 'Retry saving result' }}
            </button>
            <button
              v-if="pendingSubmission.trialType === 'study'"
              class="button button--quiet"
              type="button"
              :disabled="reconcilingResult"
              @click="refreshAfterSubmissionError"
            >
              {{ reconcilingResult ? 'Checking status…' : 'Check server status' }}
            </button>
          </div>
        </template>
      </section>

      <section v-else-if="tutorialFeedback" class="message-card study-message">
        <span class="eyebrow">
          Practice {{ tutorialFeedback.sequence }} of {{ tutorialFeedback.total_trials }}
        </span>
        <h1 v-if="tutorialFeedback.correct">Correct</h1>
        <h1 v-else-if="tutorialFeedback.timed_out">Time ran out</h1>
        <h1 v-else>Not quite</h1>

        <BaseAlert
          :tone="tutorialFeedback.correct ? 'success' : 'error'"
          :title="tutorialFeedback.correct ? 'You identified the target' : 'Use the feedback and continue'"
        >
          <p v-if="tutorialFeedback.correct">
            Your selection matched the target ampoule.
          </p>
          <p v-else-if="tutorialFeedback.timed_out">
            No selection was made before the deadline. The real study records this as a timeout.
          </p>
          <p v-else>
            Your selection did not match the target. Check the target name carefully on the next practice trial.
          </p>
        </BaseAlert>

        <p>
          Practice answers are kept separate and are not included in the study results.
        </p>
        <button class="button button--primary" type="button" @click="continueAfterTutorialFeedback">
          {{ status.phase === 'tutorial' ? 'Continue practice' : 'Continue to study instructions' }}
        </button>
      </section>

      <section v-else-if="loadingTrial" class="message-card study-message" aria-busy="true">
        <span class="spinner spinner--large" aria-hidden="true"></span>
        <span class="eyebrow">{{ status.phase === 'tutorial' ? 'Next practice trial' : 'Next trial' }}</span>
        <h1>Preparing your ampoules</h1>
        <p class="lede" role="status">
          Fetching the next server-assigned {{ status.phase === 'tutorial' ? 'practice trial' : 'trial' }}…
        </p>
      </section>

      <section v-else class="study-overview">
        <div class="overview-copy">
          <span class="eyebrow">
            {{ status.phase === 'tutorial' ? 'Practice tutorial' : status.phase === 'completed' ? 'Study complete' : 'Study checkpoint' }}
          </span>
          <h1>{{ phaseHeading }}</h1>
          <p class="lede">{{ phaseDescription }}</p>

          <BaseAlert v-if="sessionError" tone="error"><p>{{ sessionError }}</p></BaseAlert>
          <BaseAlert v-if="trialError" tone="error" title="Trial unavailable">
            <p>{{ trialError }}</p>
          </BaseAlert>

          <template v-if="status.phase === 'tutorial'">
            <BaseAlert tone="info" title="Practice is separate from the study results">
              <p>
                You will receive immediate feedback here. These practice answers are not included in
                the study analysis.
              </p>
            </BaseAlert>

            <ul class="instruction-list">
              <li>
                Practice trials mix Industry, ISO and black-and-white presentation styles; the real
                study then presents each style as a group.
              </li>
              <li>
                Use a computer with a mouse and keyboard if possible, and use the same device and input
                method for practice and the real study.
              </li>
              <li>
                With a keyboard, use Tab to move between options and Enter or Space to select. A mouse
                is recommended where available.
              </li>
              <li>
                The target and all choices appear together. If the timer expires, the practice trial is
                marked as a timeout.
              </li>
            </ul>

            <button class="button button--primary" type="button" :disabled="loadingTrial" @click="loadNextTrial">
              {{ actionLabel }}
            </button>
          </template>

          <template v-else-if="status.phase !== 'completed'">
            <ul class="instruction-list">
              <li>The target drug and all choices appear at the same time.</li>
              <li>Select one ampoule using a pointer or the keyboard before time runs out.</li>
              <li>If the timer expires, a no-selection result is saved automatically.</li>
            </ul>

            <button class="button button--primary" type="button" :disabled="loadingTrial" @click="loadNextTrial">
              {{ actionLabel }}
            </button>
          </template>

          <template v-else>
            <BaseAlert tone="success" title="All responses saved">
              <p>You may now close this window or sign out below.</p>
            </BaseAlert>
          </template>
        </div>

        <aside class="configuration-card" aria-label="Your study configuration">
          <span class="eyebrow">{{ status.phase === 'tutorial' ? 'Practice configuration' : 'Your configuration' }}</span>
          <dl v-if="status.phase === 'tutorial'">
            <div>
              <dt>{{ status.tutorial.total_trials }}</dt>
              <dd>practice trials</dd>
            </div>
            <div>
              <dt>3</dt>
              <dd>mixed styles</dd>
            </div>
            <div>
              <dt>{{ status.choices_per_trial }}</dt>
              <dd>ampoules per trial</dd>
            </div>
            <div>
              <dt>{{ timeLimitSeconds }}s</dt>
              <dd>per selection</dd>
            </div>
          </dl>
          <dl v-else>
            <div>
              <dt>{{ status.groups_total }}</dt>
              <dd>groups</dd>
            </div>
            <div>
              <dt>{{ status.trials_per_group }}</dt>
              <dd>trials per group</dd>
            </div>
            <div>
              <dt>{{ status.choices_per_trial }}</dt>
              <dd>ampoules per trial</dd>
            </div>
            <div>
              <dt>{{ timeLimitSeconds }}s</dt>
              <dd>per selection</dd>
            </div>
          </dl>
          <p v-if="status.phase !== 'tutorial' && status.current_group_name">
            Current style: <strong>{{ status.current_group_name }}</strong>
          </p>
        </aside>

        <button
          class="sign-out-link"
          type="button"
          :disabled="loggingOut"
          @click="signOut"
        >
          {{ loggingOut ? 'Signing out…' : 'Sign out on this device' }}
        </button>
      </section>
    </div>
  </div>
</template>

<style scoped>
.study-page {
  min-height: calc(100vh - 12rem);
  padding-top: clamp(2rem, 5vw, 4rem);
  padding-bottom: clamp(3rem, 7vw, 6rem);
}

.study-shell {
  display: grid;
  gap: clamp(2rem, 5vw, 3.5rem);
  width: 100%;
  padding: clamp(1.2rem, 3vw, 2rem);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-lg);
}

.study-message {
  margin-inline: auto;
}

.study-overview {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(16rem, 0.5fr);
  gap: clamp(2rem, 7vw, 5rem);
  align-items: start;
}

.overview-copy {
  display: grid;
  justify-items: start;
  gap: 1.25rem;
}

.overview-copy h1 {
  max-width: 15ch;
  margin: 0;
  font-size: clamp(2.2rem, 5.5vw, 4.6rem);
  line-height: 1;
  letter-spacing: -0.05em;
}

.instruction-list {
  display: grid;
  gap: 0.75rem;
  margin: 0;
  padding-left: 1.4rem;
  color: var(--ink-muted);
}

.configuration-card {
  display: grid;
  gap: 1.25rem;
  padding: 1.5rem;
  border-radius: var(--radius-md);
  background: var(--navy);
  color: white;
}

.configuration-card .eyebrow {
  color: var(--teal-light);
}

.configuration-card dl {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1rem;
  margin: 0;
}

.configuration-card dl div {
  display: grid;
  gap: 0.15rem;
  padding: 1rem;
  border: 1px solid rgba(255, 255, 255, 0.13);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.05);
}

.configuration-card dt {
  font-size: clamp(1.4rem, 4vw, 2rem);
  font-weight: 800;
}

.configuration-card dd {
  margin: 0;
  color: rgba(255, 255, 255, 0.68);
  font-size: 0.78rem;
}

.configuration-card p {
  margin: 0;
  color: rgba(255, 255, 255, 0.72);
}

.configuration-card strong {
  color: white;
}

.sign-out-link {
  grid-column: 1 / -1;
  justify-self: center;
  border: 0;
  border-bottom: 1px solid currentColor;
  background: transparent;
  color: var(--ink-muted);
  font: inherit;
  font-size: 0.85rem;
  cursor: pointer;
}

.sign-out-link:disabled {
  opacity: 0.6;
  cursor: wait;
}

@media (max-width: 790px) {
  .study-overview {
    grid-template-columns: 1fr;
  }
}
</style>
