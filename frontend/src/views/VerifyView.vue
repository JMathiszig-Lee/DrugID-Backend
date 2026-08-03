<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { verifyMagicLink } from '../api/study'
import { ApiError } from '../api/client'
import BaseAlert from '../components/BaseAlert.vue'

type VerifyState = 'verifying' | 'missing' | 'failed'

const route = useRoute()
const router = useRouter()
const state = ref<VerifyState>('verifying')
const errorMessage = ref('')
let token = ''

async function verify(): Promise<void> {
  if (!token) {
    state.value = 'missing'
    return
  }

  state.value = 'verifying'
  errorMessage.value = ''

  try {
    await verifyMagicLink(token)
    await router.replace({ name: 'study' })
  } catch (error) {
    state.value = 'failed'
    errorMessage.value =
      error instanceof ApiError
        ? error.message
        : 'The link could not be verified. Check your connection and try again.'
  }
}

onMounted(async () => {
  const hashParameters = new URLSearchParams(route.hash.replace(/^#/, ''))
  token = hashParameters.get('token') ?? ''

  if (route.hash) {
    await router.replace({ name: 'verify' })
  }

  await verify()
})
</script>

<template>
  <div class="page centre-page">
    <section class="message-card">
      <template v-if="state === 'verifying'">
        <span class="spinner spinner--large" aria-hidden="true"></span>
        <span class="eyebrow">Secure sign-in</span>
        <h1>Opening your study session</h1>
        <p class="lede" role="status">Please wait while we verify your one-time link.</p>
      </template>

      <template v-else-if="state === 'missing'">
        <span class="eyebrow">Link required</span>
        <h1>This sign-in link is incomplete</h1>
        <BaseAlert tone="error">
          <p>Request a new email and use the complete link it contains.</p>
        </BaseAlert>
        <RouterLink class="button button--primary" :to="{ name: 'register' }">Request a new link</RouterLink>
      </template>

      <template v-else>
        <span class="eyebrow">Link not accepted</span>
        <h1>This study link may have expired</h1>
        <BaseAlert tone="error" title="We could not sign you in">
          <p>{{ errorMessage }}</p>
        </BaseAlert>
        <div class="button-row button-row--centre">
          <button class="button button--quiet" type="button" @click="verify">Try this link again</button>
          <RouterLink class="button button--primary" :to="{ name: 'register' }">
            Request a new link
          </RouterLink>
        </div>
      </template>
    </section>
  </div>
</template>
