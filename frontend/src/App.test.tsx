import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { App } from './App'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

test('operator publishes a fixed scenario with CSRF and sees a real delivery', async () => {
  document.cookie = 'eventflow_csrf=test-csrf; path=/'
  const calls: Array<{ path: string; init: RequestInit }> = []
  const fakeFetch = vi.fn(async (input: string, init: RequestInit = {}) => {
    calls.push({ path: input, init })
    const json = (body: unknown, status = 200) =>
      new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
      })
    if (input === '/api/v1/session' && !init.method) return json({ code: 'unauthorized' }, 401)
    if (input === '/api/v1/session/login')
      return json({
        username: 'operador',
        organization_id: 'org',
        operator_id: 'op',
        expires_at: '2030-01-01T00:00:00Z',
      })
    if (input === '/api/v1/demo/scenarios')
      return json({ items: [{ id: 'success', event_type: 'demo.success', ready: true }] })
    if (input === '/api/v1/management/metrics')
      return json({ events: 0, deliveries: {}, attempts: {}, mean_attempt_duration_ms: null })
    if (input.startsWith('/api/v1/management/events?'))
      return json({ items: [], next_cursor: null })
    if (input === '/api/v1/demo/scenarios/success/events')
      return json({ event_id: 'event-1', delivery_id: 'delivery-1' }, 202)
    if (input === '/api/v1/management/deliveries/delivery-1')
      return json({
        id: 'delivery-1',
        event_id: 'event-1',
        endpoint_id: 'endpoint-1',
        status: 'pending',
        generation: 1,
        attempt_count: 0,
        next_attempt_at: null,
        endpoint_pause_until: null,
        created_at: '2030-01-01T00:00:00Z',
      })
    if (input.startsWith('/api/v1/management/deliveries/delivery-1/attempts'))
      return json({ items: [], next_cursor: null })
    if (input === '/api/v1/management/deliveries/delivery-1/receiver-observation')
      return json({ delivery_id: 'delivery-1', generations: [] })
    throw new Error(`Unexpected request ${input}`)
  })
  vi.stubGlobal('fetch', fakeFetch)

  render(<App />)
  fireEvent.change(await screen.findByLabelText('Usuario'), { target: { value: 'operador' } })
  fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'password' } })
  fireEvent.click(screen.getByRole('button', { name: 'Entrar a la consola' }))
  fireEvent.click(await screen.findByRole('button', { name: /Ejecutar escenario/ }))
  await screen.findByText(/Evento event-1 aceptado/)
  await screen.findByText('delivery-1')
  const publish = calls.find((call) => call.path === '/api/v1/demo/scenarios/success/events')
  expect(publish).toBeDefined()
  expect(new Headers(publish!.init.headers).get('X-CSRF-Token')).toBe('test-csrf')
  expect(calls.every((call) => !new Headers(call.init.headers).has('Authorization'))).toBe(true)
  await waitFor(() =>
    expect(screen.getByText('Esperando el primer intento del worker…')).toBeInTheDocument(),
  )
})
