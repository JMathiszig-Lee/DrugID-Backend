<script setup lang="ts">
import { computed } from 'vue'
import type { TutorialStatus } from '../types/study'

const props = defineProps<{
  tutorial: TutorialStatus
}>()

const percentage = computed(() => {
  if (props.tutorial.total_trials <= 0) return 0
  return Math.min(
    100,
    Math.round((props.tutorial.completed_trials / props.tutorial.total_trials) * 100),
  )
})
</script>

<template>
  <section class="progress-card progress-card--practice" aria-label="Practice progress">
    <div class="progress-copy">
      <div>
        <span class="eyebrow">Practice before the study</span>
        <strong>Industry, ISO and black-and-white styles</strong>
      </div>
      <span>{{ tutorial.completed_trials }} of {{ tutorial.total_trials }} practice trials</span>
    </div>

    <div
      class="progress-track"
      role="progressbar"
      :aria-valuenow="tutorial.completed_trials"
      aria-valuemin="0"
      :aria-valuemax="tutorial.total_trials"
      :aria-label="`${tutorial.completed_trials} of ${tutorial.total_trials} practice trials complete`"
    >
      <span :style="{ width: `${percentage}%` }"></span>
    </div>
  </section>
</template>

<style scoped>
.progress-card {
  display: grid;
  gap: 0.65rem;
}

.progress-copy {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: end;
  color: var(--ink-muted);
  font-size: 0.9rem;
}

.progress-copy > div {
  display: grid;
  gap: 0.15rem;
}

.progress-copy strong {
  color: var(--ink);
}

.progress-track {
  height: 0.65rem;
  overflow: hidden;
  border-radius: 999px;
  background: var(--amber-soft);
}

.progress-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--amber), var(--teal));
  transition: width 220ms ease;
}

@media (max-width: 520px) {
  .progress-copy {
    align-items: start;
    flex-direction: column;
    gap: 0.35rem;
  }
}
</style>
