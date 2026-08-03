import { apiRequest } from './client'
import type {
  MagicLinkRequest,
  MagicLinkResponse,
  NextTrialResponse,
  StudySessionStatus,
  TrialResultRequest,
  TrialResultResponse,
  TutorialTrialResultResponse,
  VerifyResponse,
} from '../types/study'

export function requestMagicLink(details: MagicLinkRequest): Promise<MagicLinkResponse> {
  return apiRequest('/api/auth/magic-link/', { method: 'POST', body: details })
}

export function verifyMagicLink(token: string): Promise<VerifyResponse> {
  return apiRequest('/api/auth/verify/', { method: 'POST', body: { token } })
}

export function logOut(): Promise<void> {
  return apiRequest('/api/auth/logout/', { method: 'POST', authenticated: true })
}

export function getStudySession(): Promise<StudySessionStatus> {
  return apiRequest('/api/study/session/')
}

export function getNextTrial(): Promise<NextTrialResponse> {
  return apiRequest('/api/study/trials/next/', { method: 'POST', authenticated: true })
}

export function getNextTutorialTrial(): Promise<NextTrialResponse> {
  return apiRequest('/api/study/tutorial/trials/next/', {
    method: 'POST',
    authenticated: true,
  })
}

export function submitTrialResult(
  trialId: number,
  result: TrialResultRequest,
): Promise<TrialResultResponse> {
  return apiRequest(`/api/study/trials/${encodeURIComponent(trialId)}/result/`, {
    method: 'POST',
    body: result,
    authenticated: true,
  })
}

export function submitTutorialTrialResult(
  trialId: number,
  result: TrialResultRequest,
): Promise<TutorialTrialResultResponse> {
  return apiRequest(`/api/study/tutorial/trials/${encodeURIComponent(trialId)}/result/`, {
    method: 'POST',
    body: result,
    authenticated: true,
  })
}
