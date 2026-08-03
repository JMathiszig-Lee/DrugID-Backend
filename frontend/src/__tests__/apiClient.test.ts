import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiRequest, readCookie } from '../api/client'
import { getNextTutorialTrial, submitTutorialTrialResult } from '../api/study'

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  document.cookie = 'csrftoken=; Max-Age=0; path=/'
  vi.unstubAllGlobals()
})

describe('readCookie', () => {
  it('reads and decodes an exact cookie name', () => {
    expect(readCookie('csrftoken', 'theme=dark; csrftoken=a%2Fb%20c; session=x')).toBe('a/b c')
  })

  it('does not match partial cookie names', () => {
    expect(readCookie('csrftoken', 'oldcsrftoken=nope')).toBeNull()
  })
})

describe('apiRequest', () => {
  it('always sends same-origin credentials', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ phase: 'ready' }))
    vi.stubGlobal('fetch', fetchMock)

    await apiRequest('/api/study/session/')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/study/session/',
      expect.objectContaining({ method: 'GET', credentials: 'include' }),
    )
  })

  it('adds the CSRF cookie to authenticated unsafe requests', async () => {
    document.cookie = 'csrftoken=secure%2Ftoken; path=/'
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: { phase: 'in_progress' } }))
    vi.stubGlobal('fetch', fetchMock)

    await apiRequest('/api/study/trials/next/', {
      method: 'POST',
      authenticated: true,
    })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/study/trials/next/',
      expect.objectContaining({
        credentials: 'include',
        headers: expect.objectContaining({ 'X-CSRFToken': 'secure/token' }),
      }),
    )
  })

  it('does not send a CSRF header on unauthenticated magic-link requests', async () => {
    document.cookie = 'csrftoken=unused; path=/'
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ detail: 'sent' }))
    vi.stubGlobal('fetch', fetchMock)

    await apiRequest('/api/auth/magic-link/', { method: 'POST', body: { email: 'test@example.test' } })

    const request = fetchMock.mock.calls[0]?.[1] as RequestInit
    expect(request.headers).not.toHaveProperty('X-CSRFToken')
  })

  it('stops an authenticated POST when the CSRF cookie is missing', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      apiRequest('/api/study/trials/next/', { method: 'POST', authenticated: true }),
    ).rejects.toMatchObject({ status: 403 })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('surfaces a server detail and status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: 'Link expired.' }, 401)))

    await expect(apiRequest('/api/study/session/')).rejects.toEqual(
      expect.objectContaining({ status: 401, message: 'Link expired.' }),
    )
  })

  it('turns DRF field errors into an actionable message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            email: ['Enter a valid email address.'],
            years_experience: ['Ensure this value is greater than or equal to 0.'],
          },
          400,
        ),
      ),
    )

    await expect(apiRequest('/api/auth/magic-link/', { method: 'POST', body: {} })).rejects.toEqual(
      expect.objectContaining({
        message:
          'Email: Enter a valid email address. Years experience: Ensure this value is greater than or equal to 0.',
      }),
    )
  })

  it('turns a network failure into a retryable API error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))

    await expect(apiRequest('/api/study/session/')).rejects.toMatchObject({
      status: 0,
      message: 'Unable to reach the server. Check your connection and try again.',
    })
  })

  it('rejects non-API paths', async () => {
    await expect(apiRequest('https://example.test/data')).rejects.toThrow('same-origin /api/ path')
  })

  it('uses dedicated tutorial endpoints and never the study result path', async () => {
    document.cookie = 'csrftoken=tutorial-token; path=/'
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ status: { phase: 'tutorial' }, trial: null }))
      .mockResolvedValueOnce(
        jsonResponse({
          status: { phase: 'tutorial' },
          feedback: { correct: true, timed_out: false, sequence: 1, total_trials: 6 },
        }),
      )
    vi.stubGlobal('fetch', fetchMock)

    await getNextTutorialTrial()
    await submitTutorialTrialResult(17, {
      selected_asset_id: 4,
      response_time_ms: 612,
    })

    expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
      '/api/study/tutorial/trials/next/',
      '/api/study/tutorial/trials/17/result/',
    ])
    expect(fetchMock.mock.calls[1]?.[1]).toEqual(
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ selected_asset_id: 4, response_time_ms: 612 }),
      }),
    )
  })
})
