import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api, ApiFailure } from './api'
import type { Attempt, Delivery, EventItem, Metrics, Observation, Page, Scenario, Session } from './api'

const descriptions: Record<string, { title: string; detail: string; expected: string }> = {
  success: { title: 'Entrega correcta', detail: 'El receptor confirma el primer intento.', expected: '200 al primer envío' },
  transient: { title: 'Fallo transitorio', detail: 'Dos respuestas 503 activan reintentos antes del éxito.', expected: '503 → 503 → 200' },
  'rate-limit': { title: 'Límite del destino', detail: 'El receptor responde 429 y pausa solo su endpoint.', expected: '429 → pausa → 200' },
  replay: { title: 'Dead letter y replay', detail: 'Agota siete intentos; luego un replay abre otra generación.', expected: '503 → dead letter → replay → 200' },
}

function date(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'medium' }) : '—'
}

function message(error: unknown): string {
  if (error instanceof ApiFailure) return `${error.message} (${error.code})`
  return error instanceof Error ? error.message : 'Error inesperado'
}

export function App() {
  const [session, setSession] = useState<Session | null>(null)
  const [checking, setChecking] = useState(true)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loginBusy, setLoginBusy] = useState(false)
  const [error, setError] = useState('')
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [events, setEvents] = useState<EventItem[]>([])
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [eventCursor, setEventCursor] = useState<string | null>(null)
  const [selected, setSelected] = useState<Delivery | null>(null)
  const [attempts, setAttempts] = useState<Attempt[]>([])
  const [observation, setObservation] = useState<Observation | null>(null)
  const [observationError, setObservationError] = useState('')
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState('')

  const loadEvents = useCallback(async (cursor?: string | null) => {
    const params = new URLSearchParams({ limit: '10' })
    if (cursor) params.set('cursor', cursor)
    const page = await api<Page<EventItem>>(`/api/v1/management/events?${params}`)
    setEvents((previous) => cursor ? [...previous, ...page.items] : page.items)
    setEventCursor(page.next_cursor)
  }, [])

  const loadDelivery = useCallback(async (deliveryId: string) => {
    const [delivery, history] = await Promise.all([
      api<Delivery>(`/api/v1/management/deliveries/${deliveryId}`),
      api<Page<Attempt>>(`/api/v1/management/deliveries/${deliveryId}/attempts?limit=100`),
    ])
    setSelected(delivery)
    setAttempts(history.items)
    try {
      const receiver = await api<Observation>(`/api/v1/management/deliveries/${deliveryId}/receiver-observation`)
      setObservation(receiver)
      setObservationError('')
    } catch (error) {
      setObservation(null)
      setObservationError(message(error))
    }
  }, [])

  const loadDashboard = useCallback(async () => {
    const [scenarioList, summary] = await Promise.all([
      api<{ items: Scenario[] }>('/api/v1/demo/scenarios'),
      api<Metrics>('/api/v1/management/metrics'),
      loadEvents(),
    ])
    setScenarios(scenarioList.items)
    setMetrics(summary)
  }, [loadEvents])

  useEffect(() => {
    api<Session>('/api/v1/session')
      .then((value) => { setSession(value); return loadDashboard() })
      .catch((error) => { if (!(error instanceof ApiFailure && error.status === 401)) setError(message(error)) })
      .finally(() => setChecking(false))
  }, [loadDashboard])

  useEffect(() => {
    if (!selected) return
    const timer = window.setInterval(() => {
      loadDelivery(selected.id).catch((error) => setError(message(error)))
    }, 3000)
    return () => window.clearInterval(timer)
  }, [selected?.id, loadDelivery])

  async function login(event: FormEvent) {
    event.preventDefault()
    setLoginBusy(true)
    setError('')
    try {
      const value = await api<Session>('/api/v1/session/login', {
        method: 'POST', body: JSON.stringify({ username, password }),
      })
      setPassword('')
      setSession(value)
      await loadDashboard()
    } catch (cause) { setError(message(cause)) }
    finally { setLoginBusy(false) }
  }

  async function logout() {
    setBusy('logout')
    setError('')
    try {
      await api<void>('/api/v1/session/logout', { method: 'POST' })
      setSession(null)
      setSelected(null)
      setEvents([])
      setScenarios([])
    } catch (cause) { setError(message(cause)) }
    finally { setBusy('') }
  }

  async function runScenario(id: string) {
    setBusy(id)
    setError('')
    setNotice('')
    try {
      const result = await api<{ event_id: string; delivery_id: string }>(`/api/v1/demo/scenarios/${id}/events`, { method: 'POST' })
      setNotice(`Evento ${result.event_id} aceptado. La entrega se actualizará automáticamente.`)
      await Promise.all([loadDashboard(), loadDelivery(result.delivery_id)])
      document.getElementById('delivery-detail')?.focus()
    } catch (cause) { setError(message(cause)) }
    finally { setBusy('') }
  }

  async function openEvent(id: string) {
    setBusy(`event-${id}`)
    setError('')
    try {
      const page = await api<Page<Delivery>>(`/api/v1/management/deliveries?event_id=${encodeURIComponent(id)}`)
      if (page.items.length === 0) setNotice('Este evento no tiene entregas.')
      else await loadDelivery(page.items[0].id)
    } catch (cause) { setError(message(cause)) }
    finally { setBusy('') }
  }

  async function replay() {
    if (!selected || selected.status !== 'dead_lettered') return
    setBusy('replay')
    setError('')
    try {
      await api(`/api/v1/management/deliveries/${selected.id}/replay`, { method: 'POST' })
      setNotice('Replay solicitado. Se abrió una nueva generación de intentos.')
      await loadDelivery(selected.id)
      await loadDashboard()
    } catch (cause) { setError(message(cause)) }
    finally { setBusy('') }
  }

  if (checking) return <main className="center-page" role="status">Cargando sesión…</main>

  if (!session) return <main className="login-page">
    <section className="login-intro">
      <span className="eyebrow">EVENTFLOW / CONSOLA</span>
      <h1>Observa cada entrega, desde la aceptación hasta el último intento.</h1>
      <p>Una demostración sobre eventos y webhooks reales. Explora reintentos, pausas y replay sin abrir la base de datos.</p>
      <div className="flow-line"><span>01 · Publicar</span><span>02 · Entregar</span><span>03 · Verificar</span></div>
    </section>
    <section className="login-card" aria-labelledby="login-title">
      <span className="eyebrow">ACCESO DE OPERADOR</span>
      <h2 id="login-title">Iniciar sesión</h2>
      <p>Usa las credenciales de operador asignadas a la organización de demo.</p>
      <form onSubmit={login}>
        <label htmlFor="username">Usuario</label>
        <input id="username" autoComplete="username" required value={username} onChange={(event) => setUsername(event.target.value)} />
        <label htmlFor="password">Contraseña</label>
        <input id="password" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} />
        <button type="submit" disabled={loginBusy}>{loginBusy ? 'Entrando…' : 'Entrar a la consola'}</button>
      </form>
      {error && <p className="alert" role="alert">{error}</p>}
    </section>
  </main>

  return <div className="app-shell">
    <header className="topbar">
      <div className="brand"><span className="brand-mark">↗</span><span>EventFlow</span><span className="brand-suffix">/ consola</span></div>
      <div className="operator"><span className="operator-name">{session.username}</span><button className="text-button" onClick={logout} disabled={busy === 'logout'}>Salir</button></div>
    </header>
    <main className="content">
      <div className="page-heading"><div><span className="eyebrow">LABORATORIO DE ENTREGAS</span><h1>Del evento al webhook</h1><p>Selecciona un escenario y sigue su estado desde el backend en tiempo real.</p></div><span className="live-pill"><span className="live-dot" /> Sesión activa</span></div>
      {error && <div className="alert" role="alert">{error}</div>}
      {notice && <div className="notice" role="status">{notice}</div>}
      {metrics && <section className="metric-grid" aria-label="Métricas de la organización">
        <div><span>Eventos</span><strong>{metrics.events}</strong></div>
        <div><span>Entregas correctas</span><strong>{metrics.deliveries.succeeded ?? 0}</strong></div>
        <div><span>En espera o reintento</span><strong>{(metrics.deliveries.pending ?? 0) + (metrics.deliveries.retry_scheduled ?? 0)}</strong></div>
        <div><span>Intento medio</span><strong>{metrics.mean_attempt_duration_ms == null ? '—' : `${Math.round(metrics.mean_attempt_duration_ms)} ms`}</strong></div>
      </section>}
      <section aria-labelledby="scenarios-title">
        <div className="section-heading"><div><span className="eyebrow">PASO 01</span><h2 id="scenarios-title">Inicia un escenario</h2></div><span className="section-hint">Cada ejecución crea un evento nuevo</span></div>
        <div className="scenario-grid">{scenarios.map((scenario, index) => {
          const info = descriptions[scenario.id]
          return <article className="scenario-card" key={scenario.id}>
            <div className="card-top"><span className="scenario-number">0{index + 1}</span><span className={`readiness ${scenario.ready ? 'ready' : ''}`}>{scenario.ready ? 'Preparado' : 'Sin configurar'}</span></div>
            <h3>{info?.title ?? scenario.id}</h3><p>{info?.detail}</p><span className="expected">{info?.expected}</span>
            <button onClick={() => runScenario(scenario.id)} disabled={!scenario.ready || busy !== ''}>{busy === scenario.id ? 'Publicando…' : 'Ejecutar escenario'} <span aria-hidden="true">↗</span></button>
          </article>
        })}</div>
        {scenarios.length === 0 && <p className="empty">No hay escenarios configurados para esta organización.</p>}
      </section>
      <div className="lower-grid">
        <section className="panel" aria-labelledby="events-title"><div className="section-heading"><div><span className="eyebrow">PASO 02</span><h2 id="events-title">Eventos recientes</h2></div><button className="text-button" onClick={() => loadEvents().catch((cause) => setError(message(cause)))}>Actualizar</button></div>
          {events.length ? <ul className="event-list">{events.map((event) => <li key={event.id}><button onClick={() => openEvent(event.id)} disabled={busy === `event-${event.id}`}><span><strong>{event.type}</strong><small>{date(event.created_at)}</small></span><span className="row-arrow" aria-hidden="true">→</span></button></li>)}</ul> : <p className="empty">Aún no hay eventos. Ejecuta un escenario para comenzar.</p>}
          {eventCursor && <button className="secondary-button" onClick={() => loadEvents(eventCursor).catch((cause) => setError(message(cause)))}>Cargar más eventos</button>}
        </section>
        <section className="panel detail-panel" id="delivery-detail" tabIndex={-1} aria-labelledby="detail-title"><div className="section-heading"><div><span className="eyebrow">PASO 03</span><h2 id="detail-title">Seguimiento de entrega</h2></div>{selected && <span className={`status status-${selected.status}`}>{selected.status.replace('_', ' ')}</span>}</div>
          {!selected ? <p className="empty">Selecciona un evento para ver su entrega, intentos y respuesta del receptor.</p> : <>
            <dl className="facts"><div><dt>ID de entrega</dt><dd className="mono">{selected.id}</dd></div><div><dt>Generación</dt><dd>{selected.generation}</dd></div><div><dt>Intentos</dt><dd>{selected.attempt_count}</dd></div><div><dt>Próximo intento</dt><dd>{date(selected.next_attempt_at)}</dd></div><div><dt>Pausa del endpoint</dt><dd>{date(selected.endpoint_pause_until)}</dd></div></dl>
            {selected.status === 'dead_lettered' && <button className="replay-button" onClick={replay} disabled={busy === 'replay'}>{busy === 'replay' ? 'Solicitando…' : 'Reproducir entrega'}</button>}
            <h3 className="detail-subhead">Historia de intentos</h3>
            {attempts.length ? <ol className="attempt-list">{attempts.map((attempt) => <li key={attempt.id}><span className="attempt-dot" /><div><strong>Intento {attempt.number} · generación {attempt.generation}</strong><small>{date(attempt.started_at)}</small></div><span>{attempt.response_status ?? attempt.error_category ?? attempt.status}</span></li>)}</ol> : <p className="empty compact">Esperando el primer intento del worker…</p>}
            <h3 className="detail-subhead">Receptor externo</h3>
            {observationError && <p className="quiet">Observación no disponible: {observationError}</p>}
            {observation && (observation.generations.length ? <ul className="receiver-list">{observation.generations.map((item) => <li key={item.generation}>Generación {item.generation}: firma {item.signature_verified ? 'verificada' : 'sin verificar'}, {item.request_count} petición(es), último HTTP {item.last_status}{item.processed ? ', procesada' : ''}.</li>)}</ul> : <p className="empty compact">El receptor aún no ha recibido esta entrega.</p>)}
          </>}
        </section>
      </div>
    </main>
    <footer>EventFlow · Entrega al menos una vez · Los intentos pueden repetirse</footer>
  </div>
}
