export type StudyPhase = 'tutorial' | 'ready' | 'in_progress' | 'between_groups' | 'completed'
export type TrialType = 'tutorial' | 'study'

export interface MagicLinkRequest {
  email: string
  speciality: string
  years_experience: number
}

export interface ReturningMagicLinkRequest {
  email: string
}

export interface MagicLinkResponse {
  detail: string
  debug_magic_link?: string
}

export interface StudySessionStatus {
  id: string | number
  phase: StudyPhase
  group_index: number | null
  groups_total: number
  current_group_name: string | null
  completed_trials: number
  total_trials: number
  completed_in_group: number
  trials_per_group: number
  choices_per_trial: number
  time_limit_ms: number
  has_active_trial: boolean
  tutorial: TutorialStatus
}

export interface TutorialStatus {
  required: number
  complete: boolean
  completed_trials: number
  total_trials: number
  has_active_trial: boolean
}

export interface VerifyResponse {
  detail: string
  session: StudySessionStatus
}

export interface AmpouleAsset {
  id: number
  image_url: string
}

export interface StudyTrial {
  id: number
  trial_type: TrialType
  storage_key: string
  sequence: number
  sequence_total: number
  group_index: number | null
  style_name: string
  target_drug: string
  time_limit_ms: number
  ampoules: AmpouleAsset[]
}

export interface NextTrialResponse {
  status: StudySessionStatus
  trial: StudyTrial | null
}

export interface TrialResultRequest {
  selected_asset_id: number | null
  response_time_ms: number
}

export interface TrialResultResponse {
  status: StudySessionStatus
}

export interface TutorialFeedback {
  correct: boolean
  timed_out: boolean
  sequence: number
  total_trials: number
}

export interface TutorialTrialResultResponse {
  status: StudySessionStatus
  feedback: TutorialFeedback
}

export interface TrialSelection {
  selectedAssetId: number | null
  responseTimeMs: number
}
