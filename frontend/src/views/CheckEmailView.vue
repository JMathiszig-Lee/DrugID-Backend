<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import BaseAlert from '../components/BaseAlert.vue'
import { magicLinkRequestKind, registrationResponse } from '../state/registration'

const route = useRoute()
const returningParticipant = computed(
  () => route.query.flow === 'returning' || magicLinkRequestKind.value === 'returning',
)

const retryRoute = computed(() => ({
  name: returningParticipant.value ? 'returning-participant' : 'register',
}))

const detail = computed(
  () => registrationResponse.value?.detail ?? 'If the address can take part, a study link is on its way.',
)

const debugLink = computed(() => {
  const link = registrationResponse.value?.debug_magic_link
  if (!link) return null

  try {
    const url = new URL(link, window.location.origin)
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : null
  } catch {
    return null
  }
})
</script>

<template>
  <div class="page centre-page">
    <section class="message-card">
      <div class="mail-icon" aria-hidden="true">✉</div>
      <span class="eyebrow">{{ returningParticipant ? 'Return link requested' : 'Registration link requested' }}</span>
      <h1>Check your email</h1>
      <p class="lede">{{ detail }}</p>

      <BaseAlert v-if="returningParticipant" tone="info" title="What happens next">
        <p>
          If the email is registered, the link will return you to your saved study progress. Check
          the spelling or register first if no email arrives.
        </p>
      </BaseAlert>

      <BaseAlert tone="info" title="The link is time-limited">
        <p>Open it in this browser when you are ready to begin. If it has expired, request another.</p>
      </BaseAlert>

      <BaseAlert v-if="debugLink" tone="success" title="Development shortcut">
        <p>The server returned a debug link because email delivery is in development mode.</p>
        <a class="text-link" :href="debugLink">Open the debug study link</a>
      </BaseAlert>

      <div class="button-row button-row--centre">
        <RouterLink class="button button--quiet" :to="retryRoute">
          {{ returningParticipant ? 'Request another return link' : 'Register with another email' }}
        </RouterLink>
        <RouterLink class="button button--primary" :to="{ name: 'landing' }">Return home</RouterLink>
      </div>
    </section>
  </div>
</template>
