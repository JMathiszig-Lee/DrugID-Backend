export class ApiError extends Error {
  readonly status: number
  readonly payload: unknown

  constructor(message: string, status = 0, payload: unknown = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.payload = payload
  }
}

interface ApiRequestOptions {
  method?: 'GET' | 'POST'
  body?: unknown
  authenticated?: boolean
  signal?: AbortSignal
}

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

export function readCookie(name: string, cookieSource = document.cookie): string | null {
  const prefix = `${encodeURIComponent(name)}=`

  for (const item of cookieSource.split(';')) {
    const cookie = item.trim()
    if (!cookie.startsWith(prefix)) continue

    try {
      return decodeURIComponent(cookie.slice(prefix.length))
    } catch {
      return cookie.slice(prefix.length)
    }
  }

  return null
}

function errorMessage(payload: unknown, status: number): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail
    if (typeof detail === 'string' && detail.trim()) return detail
  }

  if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
    const validationMessages = Object.entries(payload)
      .flatMap(([field, messages]) => {
        const values = Array.isArray(messages) ? messages : [messages]
        const label =
          field === 'non_field_errors'
            ? ''
            : `${field.replaceAll('_', ' ').replace(/^./, (letter) => letter.toUpperCase())}: `

        return values
          .filter((message): message is string => typeof message === 'string' && message.trim().length > 0)
          .map((message) => `${label}${message}`)
      })

    if (validationMessages.length > 0) return validationMessages.join(' ')
  }

  if (status === 401) return 'Your study session has expired. Please use a new sign-in link.'
  if (status === 403) return 'This request could not be verified. Please refresh and try again.'
  return `The server could not complete the request (${status}).`
}

async function responsePayload(response: Response): Promise<unknown> {
  if (response.status === 204) return null

  const body = await response.text()
  if (!body) return null

  try {
    return JSON.parse(body) as unknown
  } catch {
    return body
  }
}

export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  if (!path.startsWith('/api/')) {
    throw new Error(`API requests must use a same-origin /api/ path: ${path}`)
  }

  const method = options.method ?? 'GET'
  const headers: Record<string, string> = {
    Accept: 'application/json',
  }

  if (options.body !== undefined) headers['Content-Type'] = 'application/json'

  if (options.authenticated && !SAFE_METHODS.has(method)) {
    const csrfToken = readCookie('csrftoken')
    if (!csrfToken) {
      throw new ApiError(
        'The security cookie is missing. Open your study sign-in link again, then retry.',
        403,
      )
    }
    headers['X-CSRFToken'] = csrfToken
  }

  let response: Response
  try {
    response = await fetch(path, {
      method,
      credentials: 'include',
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError('Unable to reach the server. Check your connection and try again.', 0, error)
  }

  const payload = await responsePayload(response)
  if (!response.ok) throw new ApiError(errorMessage(payload, response.status), response.status, payload)

  return payload as T
}
