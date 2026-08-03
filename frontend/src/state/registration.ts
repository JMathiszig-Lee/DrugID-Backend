import { readonly, shallowRef } from 'vue'
import type { MagicLinkResponse } from '../types/study'

export type MagicLinkRequestKind = 'registration' | 'returning'

const latestResponse = shallowRef<MagicLinkResponse | null>(null)
const latestRequestKind = shallowRef<MagicLinkRequestKind>('registration')

export const registrationResponse = readonly(latestResponse)
export const magicLinkRequestKind = readonly(latestRequestKind)

export function rememberRegistrationResponse(response: MagicLinkResponse): void {
  latestResponse.value = response
  latestRequestKind.value = 'registration'
}

export function rememberReturningResponse(response: MagicLinkResponse): void {
  latestResponse.value = response
  latestRequestKind.value = 'returning'
}

export function clearRegistrationResponse(): void {
  latestResponse.value = null
  latestRequestKind.value = 'registration'
}
