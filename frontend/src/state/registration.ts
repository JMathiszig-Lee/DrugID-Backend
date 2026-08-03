import { readonly, shallowRef } from 'vue'
import type { MagicLinkResponse } from '../types/study'

const latestResponse = shallowRef<MagicLinkResponse | null>(null)

export const registrationResponse = readonly(latestResponse)

export function rememberRegistrationResponse(response: MagicLinkResponse): void {
  latestResponse.value = response
}

export function clearRegistrationResponse(): void {
  latestResponse.value = null
}
