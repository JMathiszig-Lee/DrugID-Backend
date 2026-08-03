<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { clearTrialStart, getOrCreateTrialStart } from '../lib/trialPersistence'
import { normaliseResponseTime, remainingTime } from '../lib/trialTiming'
import type { TrialSelection, StudyTrial } from '../types/study'
import BaseAlert from './BaseAlert.vue'

const props = defineProps<{
  trial: StudyTrial
}>()

const emit = defineEmits<{
  complete: [selection: TrialSelection]
}>()

const loadedIds = ref<Set<number>>(new Set())
const failedIds = ref<Set<number>>(new Set())
const optionButtons = ref<HTMLButtonElement[]>([])
const trialElement = ref<HTMLElement | null>(null)
const trialHeader = ref<HTMLElement | null>(null)
const ampouleGrid = ref<HTMLElement | null>(null)
const readyButton = ref<HTMLButtonElement | null>(null)
const imageGeneration = ref(0)
const imagesTimedOut = ref(false)
const ready = ref(false)
const layoutFits = ref(true)
const pageVisible = ref(true)
const starting = ref(false)
const displayed = ref(false)
const active = ref(false)
const finished = ref(false)
const remainingMs = ref(props.trial.time_limit_ms)

let startTime = 0
let activationFrame: number | null = null
let timerFrame: number | null = null
let imageLoadTimer: number | null = null

const IMAGE_LOAD_TIMEOUT_MS = 15_000

const isTutorial = computed(() => props.trial.trial_type === 'tutorial')
const trialLabel = computed(() => {
  const noun = isTutorial.value ? 'Practice' : 'Trial'
  return `${noun} ${props.trial.sequence} of ${props.trial.sequence_total}`
})
const trialContext = computed(() => `${trialLabel.value} · ${props.trial.style_name}`)
const startButtonLabel = computed(() =>
  starting.value
    ? `Positioning ${isTutorial.value ? 'practice' : 'trial'}…`
    : `Start ${isTutorial.value ? 'practice trial' : 'trial'}`,
)
const remainingSeconds = computed(() => (remainingMs.value / 1000).toFixed(1))
const timePercentage = computed(() => {
  if (props.trial.time_limit_ms <= 0) return 0
  return Math.max(0, Math.min(100, (remainingMs.value / props.trial.time_limit_ms) * 100))
})
const timerStyle = computed(
  () => ({ '--time-left': `${timePercentage.value}%` }) as Record<string, string>,
)
const imageLoadProblem = computed(() => {
  if (props.trial.ampoules.length === 0) return 'No ampoule images were supplied for this trial.'
  if (imagesTimedOut.value) return 'The ampoule images took too long to load.'
  if (failedIds.value.size > 0) {
    const noun = failedIds.value.size === 1 ? 'image' : 'images'
    return `${failedIds.value.size} ${noun} could not be loaded.`
  }
  return null
})
const trialBusy = computed(
  () => !displayed.value && !ready.value && imageLoadProblem.value === null,
)

function cancelFrames(): void {
  if (activationFrame !== null) cancelAnimationFrame(activationFrame)
  if (timerFrame !== null) cancelAnimationFrame(timerFrame)
  activationFrame = null
  timerFrame = null
}

function clearImageLoadTimer(): void {
  if (imageLoadTimer !== null) window.clearTimeout(imageLoadTimer)
  imageLoadTimer = null
}

function scheduleImageLoadWatchdog(): void {
  clearImageLoadTimer()
  imagesTimedOut.value = false
  imageLoadTimer = window.setTimeout(() => {
    imageLoadTimer = null
    if (loadedIds.value.size !== props.trial.ampoules.length) {
      imagesTimedOut.value = true
      ready.value = false
    }
  }, IMAGE_LOAD_TIMEOUT_MS)
}

function updateLayoutFit(): void {
  if (!ready.value || !trialHeader.value || !ampouleGrid.value) return

  const headerBounds = trialHeader.value.getBoundingClientRect()
  const gridBounds = ampouleGrid.value.getBoundingClientRect()
  layoutFits.value =
    headerBounds.top >= 0 &&
    gridBounds.bottom <= window.innerHeight &&
    gridBounds.left >= 0 &&
    gridBounds.right <= window.innerWidth
}

function scrollTrialIntoPosition(): void {
  if (!trialElement.value) return
  const root = document.documentElement
  const previousScrollBehaviour = root.style.scrollBehavior
  root.style.scrollBehavior = 'auto'
  trialElement.value.scrollIntoView({ block: 'start' })
  root.style.scrollBehavior = previousScrollBehaviour
}

function tick(now: number): void {
  if (!active.value || finished.value) return

  remainingMs.value = remainingTime(startTime, now, props.trial.time_limit_ms)
  if (remainingMs.value <= 0) {
    finish(null)
    return
  }

  timerFrame = requestAnimationFrame(tick)
}

function prepareWhenReady(): void {
  if (
    ready.value ||
    displayed.value ||
    failedIds.value.size > 0 ||
    imagesTimedOut.value ||
    props.trial.ampoules.length === 0 ||
    loadedIds.value.size !== props.trial.ampoules.length
  ) {
    return
  }

  clearImageLoadTimer()
  ready.value = true
  void nextTick(() => {
    scrollTrialIntoPosition()
    activationFrame = requestAnimationFrame(() => {
      activationFrame = null
      updateLayoutFit()
      readyButton.value?.focus({ preventScroll: true })
    })
  })
}

function startTrial(): void {
  if (
    !ready.value ||
    starting.value ||
    displayed.value ||
    finished.value ||
    document.visibilityState !== 'visible'
  ) {
    return
  }

  starting.value = true
  scrollTrialIntoPosition()
  activationFrame = requestAnimationFrame(() => {
    activationFrame = null
    updateLayoutFit()
    if (
      finished.value ||
      !layoutFits.value ||
      document.visibilityState !== 'visible'
    ) {
      starting.value = false
      return
    }

    const wallClockNow = Date.now()
    const persistedStart = getOrCreateTrialStart(props.trial.storage_key, wallClockNow)
    const elapsedBeforeThisPage = Math.max(0, wallClockNow - persistedStart)
    startTime = performance.now() - elapsedBeforeThisPage
    remainingMs.value = remainingTime(startTime, performance.now(), props.trial.time_limit_ms)
    displayed.value = true
    active.value = true
    starting.value = false
    timerFrame = requestAnimationFrame(tick)
    void nextTick(() => optionButtons.value[0]?.focus({ preventScroll: true }))
  })
}

function markLoaded(assetId: number): void {
  const next = new Set(loadedIds.value)
  next.add(assetId)
  loadedIds.value = next
  prepareWhenReady()
}

function markFailed(assetId: number): void {
  const next = new Set(failedIds.value)
  next.add(assetId)
  failedIds.value = next
  ready.value = false
  clearImageLoadTimer()
  cancelFrames()
}

function retryImages(): void {
  cancelFrames()
  loadedIds.value = new Set()
  failedIds.value = new Set()
  imageGeneration.value += 1
  imagesTimedOut.value = false
  ready.value = false
  layoutFits.value = true
  starting.value = false
  displayed.value = false
  active.value = false
  finished.value = false
  remainingMs.value = props.trial.time_limit_ms
  scheduleImageLoadWatchdog()
}

function finish(selectedAssetId: number | null): void {
  if (finished.value || !active.value) return

  const endedAt = performance.now()
  const timedOut =
    selectedAssetId === null || endedAt - startTime >= Math.max(0, props.trial.time_limit_ms)
  finished.value = true
  active.value = false
  cancelFrames()

  emit('complete', {
    selectedAssetId: timedOut ? null : selectedAssetId,
    responseTimeMs:
      timedOut
        ? Math.max(0, Math.round(props.trial.time_limit_ms))
        : normaliseResponseTime(startTime, endedAt, props.trial.time_limit_ms),
  })
  clearTrialStart(props.trial.storage_key)
}

function resetTrial(): void {
  cancelFrames()
  loadedIds.value = new Set()
  failedIds.value = new Set()
  imageGeneration.value += 1
  imagesTimedOut.value = false
  ready.value = false
  layoutFits.value = true
  starting.value = false
  displayed.value = false
  active.value = false
  finished.value = false
  remainingMs.value = props.trial.time_limit_ms
  startTime = 0
  scheduleImageLoadWatchdog()
}

watch(() => props.trial.storage_key, resetTrial)

function handleVisibilityChange(): void {
  pageVisible.value = document.visibilityState === 'visible'
}

onMounted(() => {
  pageVisible.value = document.visibilityState === 'visible'
  scheduleImageLoadWatchdog()
  window.addEventListener('resize', updateLayoutFit)
  document.addEventListener('visibilitychange', handleVisibilityChange)
})

onBeforeUnmount(() => {
  cancelFrames()
  clearImageLoadTimer()
  window.removeEventListener('resize', updateLayoutFit)
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})
</script>

<template>
  <section ref="trialElement" class="trial" :aria-busy="trialBusy">
    <header ref="trialHeader" class="trial-header">
      <div class="target-copy">
        <span class="eyebrow" :class="{ 'stimulus--concealed': !displayed }">
          {{ trialContext }}
        </span>
        <h1 id="trial-target" :class="{ 'stimulus--concealed': !displayed }">
          Select <strong>{{ trial.target_drug }}</strong>
        </h1>
        <div v-if="!displayed" class="trial-heading-placeholder">
          <span class="eyebrow">{{ trialContext }}</span>
          <h1>{{ ready ? 'Ampoules ready' : 'Preparing the next trial' }}</h1>
        </div>
      </div>

      <div
        class="timer"
        :class="{ 'stimulus--concealed': !displayed }"
        :style="timerStyle"
        role="timer"
        aria-label="Time remaining"
      >
        <strong>{{ remainingSeconds }}</strong>
        <span>seconds</span>
      </div>
    </header>

    <BaseAlert v-if="imageLoadProblem" tone="error" title="Images unavailable">
      <p>{{ imageLoadProblem }} Your timer has not started.</p>
      <button class="button button--small" type="button" @click="retryImages">Retry images</button>
    </BaseAlert>

    <div
      v-else-if="ready && !displayed"
      class="ready-panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="trial-ready-title"
    >
      <div class="ready-card">
        <span class="eyebrow">Untimed {{ isTutorial ? 'practice ' : '' }}checkpoint</span>
        <h2 id="trial-ready-title">Start when you are ready to concentrate</h2>
        <p>
          The target and ampoules are still concealed. The {{ remainingSeconds }}-second timer starts
          only when you choose
          <strong>{{ isTutorial ? 'Start practice trial' : 'Start trial' }}</strong>.
        </p>
        <BaseAlert v-if="!layoutFits" tone="error" title="More screen space is needed">
          <p>
            Enlarge this window or zoom out until the full stimulus fits. The timer has not started.
          </p>
        </BaseAlert>
        <BaseAlert v-else-if="!pageVisible" tone="error" title="Return to this tab">
          <p>The {{ isTutorial ? 'practice' : 'study' }} must be visible before a timed trial can start.</p>
        </BaseAlert>
        <button
          ref="readyButton"
          class="button button--primary"
          type="button"
          :disabled="!layoutFits || !pageVisible || starting"
          @click="startTrial"
        >
          {{ startButtonLabel }}
        </button>
      </div>
    </div>

    <div v-else-if="!displayed" class="preparing" role="status">
      <span class="spinner" aria-hidden="true"></span>
      <p>Loading every ampoule before the timer starts…</p>
    </div>

    <div ref="ampouleGrid" class="ampoule-grid" :class="{ 'ampoule-grid--concealed': !displayed }">
      <button
        v-for="(ampoule, index) in trial.ampoules"
        ref="optionButtons"
        :key="ampoule.id"
        class="ampoule-option"
        type="button"
        :disabled="!active"
        :aria-label="`Select ampoule option ${index + 1}`"
        aria-describedby="trial-target"
        @click="finish(ampoule.id)"
      >
        <img
          :key="`${ampoule.id}-${imageGeneration}`"
          :src="ampoule.image_url"
          :alt="`Ampoule option ${index + 1}`"
          draggable="false"
          @load="markLoaded(ampoule.id)"
          @error="markFailed(ampoule.id)"
        />
        <span aria-hidden="true">Option {{ index + 1 }}</span>
      </button>
    </div>
  </section>
</template>

<style scoped>
.trial {
  position: relative;
  display: grid;
  gap: clamp(1rem, 3vw, 2rem);
}

.target-copy {
  position: relative;
}

.trial-heading-placeholder {
  position: absolute;
  inset: 0 auto auto 0;
}

.stimulus--concealed {
  visibility: hidden;
}

.trial-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1.5rem;
  min-height: 5.5rem;
}

.trial-header h1 {
  margin: 0.25rem 0 0;
  font-size: clamp(1.65rem, 4vw, 2.7rem);
  font-weight: 450;
}

.trial-header h1 strong {
  color: var(--blue-dark);
  font-weight: 800;
  text-transform: uppercase;
}

.timer {
  --time-left: 100%;
  display: grid;
  place-content: center;
  flex: 0 0 6.25rem;
  width: 6.25rem;
  height: 6.25rem;
  border-radius: 50%;
  background:
    radial-gradient(circle, var(--surface) 57%, transparent 59%),
    conic-gradient(var(--teal) var(--time-left), var(--surface-strong) 0);
  text-align: center;
}

.timer strong {
  font-size: 1.45rem;
  line-height: 1;
}

.timer span {
  color: var(--ink-muted);
  font-size: 0.72rem;
}

.preparing {
  display: grid;
  justify-items: center;
  gap: 0.75rem;
  min-height: 8rem;
  padding: 2rem;
  color: var(--ink-muted);
  text-align: center;
}

.ready-panel {
  position: fixed;
  z-index: 50;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 1rem;
  background: rgba(16, 40, 62, 0.72);
}

.ready-card {
  display: grid;
  justify-items: center;
  gap: 1rem;
  width: min(100%, 36rem);
  padding: clamp(1.5rem, 5vw, 2.5rem);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-lg);
  color: var(--ink-muted);
  text-align: center;
}

.ready-panel h2,
.ready-panel p {
  margin: 0;
}

.ready-panel h2 {
  color: var(--ink);
  font-size: clamp(1.25rem, 3vw, 1.7rem);
}

.spinner {
  width: 2rem;
  height: 2rem;
  border: 3px solid var(--surface-strong);
  border-top-color: var(--blue);
  border-radius: 50%;
  animation: spin 700ms linear infinite;
}

.ampoule-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(8rem, 42vw), 1fr));
  gap: clamp(0.65rem, 2vw, 1.25rem);
  align-items: stretch;
}

.ampoule-grid--concealed {
  visibility: hidden;
  pointer-events: none;
}

.ampoule-option {
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
  gap: 0.65rem;
  justify-items: center;
  min-width: 0;
  padding: 0.85rem 0.65rem 0.7rem;
  border: 2px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface);
  color: var(--ink-muted);
  font: inherit;
  cursor: pointer;
  box-shadow: var(--shadow-sm);
  transition: border-color 120ms ease, box-shadow 120ms ease, transform 120ms ease;
}

.ampoule-option:not(:disabled):hover {
  border-color: var(--amber);
  box-shadow: 0 0 0 3px var(--amber-soft), var(--shadow-md);
  transform: translateY(-2px);
}

.ampoule-option:disabled {
  opacity: 1;
  cursor: default;
}

.ampoule-option img {
  display: block;
  width: 100%;
  max-width: 7rem;
  height: clamp(8rem, 25vh, 14rem);
  object-fit: contain;
  user-select: none;
}

.ampoule-option span {
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 620px) {
  .trial-header {
    align-items: flex-start;
  }

  .timer {
    flex-basis: 5rem;
    width: 5rem;
    height: 5rem;
  }

  .ampoule-option img {
    height: clamp(8rem, 25vh, 12rem);
  }
}

@media (prefers-reduced-motion: reduce) {
  .spinner {
    animation-duration: 1.5s;
  }

  .ampoule-option {
    transition: none;
  }
}
</style>
