export type Session = {
  operator_id: string
  organization_id: string
  username: string
  expires_at: string
}

export type Scenario = { id: string; event_type: string; ready: boolean }
export type EventItem = { id: string; type: string; created_at: string; terminal_at: string | null }
export type Delivery = {
  id: string
  event_id: string
  endpoint_id: string
  status: string
  generation: number
  attempt_count: number
  next_attempt_at: string | null
  endpoint_pause_until: string | null
  created_at: string
}
export type Attempt = {
  id: string
  number: number
  generation: number
  status: string
  response_status: number | null
  error_category: string | null
  started_at: string
  finished_at: string | null
}
export type Observation = {
  delivery_id: string
  generations: Array<{
    generation: number
    request_count: number
    signature_verified: boolean
    processed: boolean
    last_status: number
    last_received_at: number
  }>
}
export type Page<T> = { items: T[]; next_cursor: string | null }
export type Metrics = {
  events: number
  deliveries: Record<string, number>
  attempts: Record<string, number>
  mean_attempt_duration_ms: number | null
}
type ApiErrorBody = { code?: string; message?: string }

export class ApiFailure extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message)
  }
}

function csrfToken(): string {
  const cookie = document.cookie.split('; ').find((part) => part.startsWith('eventflow_csrf='))
  return cookie ? decodeURIComponent(cookie.slice('eventflow_csrf='.length)) : ''
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = options.method?.toUpperCase() ?? 'GET'
  const headers = new Headers(options.headers)
  if (method !== 'GET' && method !== 'HEAD') headers.set('X-CSRF-Token', csrfToken())
  if (options.body) headers.set('Content-Type', 'application/json')
  const response = await fetch(path, { ...options, headers, credentials: 'same-origin' })
  if (!response.ok) {
    const body: ApiErrorBody = await response.json().catch(() => ({}))
    throw new ApiFailure(
      response.status,
      body.code ?? 'request_failed',
      body.message ?? 'No se pudo completar la solicitud',
    )
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
