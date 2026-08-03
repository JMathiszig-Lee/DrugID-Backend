<script setup lang="ts">
import { computed } from 'vue'
import type { StudySessionStatus } from '../types/study'

const props = defineProps<{
  status: StudySessionStatus
}>()

const percentage = computed(() => {
  if (props.status.total_trials <= 0) return 0
  return Math.min(100, Math.round((props.status.completed_trials / props.status.total_trials) * 100))
})

const groupText = computed(() => {
  if (props.status.group_index === null) return `${props.status.groups_total} groups`
  return `Group ${props.status.group_index} of ${props.status.groups_total}`
})
</script>

<template>
  <section class="progress-card" aria-label="Study progress">
    <div class="progress-copy">
      <div>
        <span class="eyebrow">{{ groupText }}</span>
        <strong v-if="status.current_group_name">{{ status.current_group_name }}</strong>
      </div>
      <span>{{ status.completed_trials }} of {{ status.total_trials }} trials</span>
    </div>

    <div
      class="progress-track"
      role="progressbar"
      :aria-valuenow="status.completed_trials"
      aria-valuemin="0"
      :aria-valuemax="status.total_trials"
      :aria-label="`${status.completed_trials} of ${status.total_trials} trials complete`"
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
  background: var(--surface-strong);
}

.progress-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--blue), var(--teal));
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
