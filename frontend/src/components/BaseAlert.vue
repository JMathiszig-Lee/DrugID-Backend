<script setup lang="ts">
withDefaults(
  defineProps<{
    title?: string
    tone?: 'info' | 'error' | 'success'
  }>(),
  {
    title: '',
    tone: 'info',
  },
)
</script>

<template>
  <div class="alert" :class="`alert--${tone}`" :role="tone === 'error' ? 'alert' : 'status'">
    <strong v-if="title">{{ title }}</strong>
    <div><slot /></div>
  </div>
</template>

<style scoped>
.alert {
  display: grid;
  gap: 0.35rem;
  padding: 1rem 1.1rem;
  border: 1px solid var(--border-strong);
  border-left-width: 4px;
  border-radius: var(--radius-sm);
  background: var(--surface-soft);
  color: var(--ink);
}

.alert--info {
  border-left-color: var(--blue);
}

.alert--error {
  border-left-color: var(--danger);
  background: var(--danger-soft);
}

.alert--success {
  border-left-color: var(--success);
  background: var(--success-soft);
}
</style>
