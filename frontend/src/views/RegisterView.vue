<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { requestMagicLink } from '../api/study'
import { ApiError } from '../api/client'
import BaseAlert from '../components/BaseAlert.vue'
import { rememberRegistrationResponse } from '../state/registration'

const router = useRouter()
const email = ref('')
const speciality = ref('')
const yearsExperience = ref<number | null>(null)
const submitting = ref(false)
const errorMessage = ref('')
const emailError = ref('')
const duplicateEmail = ref(false)

function firstFieldError(error: ApiError, field: string): string {
  if (!error.payload || typeof error.payload !== 'object' || Array.isArray(error.payload)) return ''

  const messages = (error.payload as Record<string, unknown>)[field]
  if (Array.isArray(messages)) {
    return messages.find((message): message is string => typeof message === 'string') ?? ''
  }
  return typeof messages === 'string' ? messages : ''
}

async function submitRegistration(): Promise<void> {
  if (submitting.value || yearsExperience.value === null) return

  submitting.value = true
  errorMessage.value = ''
  emailError.value = ''
  duplicateEmail.value = false

  try {
    const response = await requestMagicLink({
      email: email.value.trim(),
      speciality: speciality.value,
      years_experience: yearsExperience.value,
    })
    rememberRegistrationResponse(response)
    await router.push({ name: 'check-email', query: { flow: 'registration' } })
  } catch (error) {
    errorMessage.value =
      error instanceof ApiError ? error.message : 'Registration could not be completed. Please try again.'
    if (error instanceof ApiError) {
      emailError.value = firstFieldError(error, 'email')
      duplicateEmail.value = emailError.value.toLowerCase().includes('already registered')
    }
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="page narrow-page">
    <section class="form-layout">
      <div class="form-intro">
        <RouterLink class="back-link" :to="{ name: 'landing' }">← Back to study information</RouterLink>
        <span class="eyebrow">New participant registration</span>
        <h1>Register to take part</h1>
        <p class="lede">
          We use these details to describe the participant group. Your test order is assigned by
          the server when you register.
        </p>

        <div class="privacy-note">
          <strong>Your email is not your score.</strong>
          <p>It is used to deliver your sign-in link and reconnect you to the correct study session.</p>
        </div>

        <p class="alternative-link">
          Already registered?
          <RouterLink class="text-link" :to="{ name: 'returning-participant' }">
            Request a return link
          </RouterLink>.
        </p>
      </div>

      <form class="form-card" @submit.prevent="submitRegistration">
        <BaseAlert v-if="errorMessage" tone="error" title="We could not send your link">
          <p>{{ errorMessage }}</p>
          <p v-if="duplicateEmail">
            <RouterLink class="text-link" :to="{ name: 'returning-participant' }">
              Request a returning-participant link instead
            </RouterLink>
          </p>
        </BaseAlert>

        <div class="field">
          <label for="email">Email address</label>
          <input
            id="email"
            v-model="email"
            name="email"
            type="email"
            autocomplete="email"
            inputmode="email"
            required
            :aria-invalid="emailError ? 'true' : undefined"
            :aria-describedby="emailError ? 'email-help email-error' : 'email-help'"
            :disabled="submitting"
            @input="emailError = ''; errorMessage = ''; duplicateEmail = false"
          />
          <small id="email-help">We will send the one-time study link here.</small>
          <small v-if="emailError" id="email-error" class="field-error">{{ emailError }}</small>
        </div>

        <div class="field">
          <label for="speciality">Clinical speciality</label>
          <select id="speciality" v-model="speciality" name="speciality" required :disabled="submitting">
            <option value="" disabled>Select your speciality</option>
            <option value="GAS">Anaesthetics</option>
            <option value="A+E">Emergency medicine</option>
            <option value="ICM">Intensive care medicine</option>
            <option value="OTH">Other</option>
          </select>
        </div>

        <div class="field">
          <label for="years-experience">Years of clinical experience</label>
          <input
            id="years-experience"
            v-model.number="yearsExperience"
            name="years_experience"
            type="number"
            min="0"
            max="80"
            step="1"
            inputmode="numeric"
            required
            :disabled="submitting"
          />
          <small>Enter 0 if you have less than one year of experience.</small>
        </div>

        <button class="button button--primary button--full" type="submit" :disabled="submitting">
          <span v-if="submitting" class="button-spinner" aria-hidden="true"></span>
          {{ submitting ? 'Sending link…' : 'Register and email my study link' }}
        </button>
      </form>
    </section>
  </div>
</template>

<style scoped>
.form-layout {
  display: grid;
  grid-template-columns: minmax(0, 0.9fr) minmax(20rem, 0.7fr);
  gap: clamp(2.5rem, 8vw, 7rem);
  align-items: start;
  padding: clamp(3rem, 7vw, 6rem) 0;
}

.form-intro {
  display: grid;
  justify-items: start;
  gap: 1.2rem;
}

.form-intro h1 {
  max-width: 12ch;
  margin: 0;
  font-size: clamp(2.5rem, 6vw, 4.7rem);
  line-height: 1;
  letter-spacing: -0.05em;
}

.privacy-note {
  max-width: 32rem;
  margin-top: 1rem;
  padding-left: 1rem;
  border-left: 3px solid var(--teal);
}

.privacy-note p,
.alternative-link {
  margin: 0.25rem 0 0;
  color: var(--ink-muted);
}

.field-error {
  color: var(--danger);
  font-weight: 750;
}

.form-card {
  display: grid;
  gap: 1.35rem;
  padding: clamp(1.35rem, 4vw, 2.25rem);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-lg);
}

@media (max-width: 800px) {
  .form-layout {
    grid-template-columns: 1fr;
  }
}
</style>
