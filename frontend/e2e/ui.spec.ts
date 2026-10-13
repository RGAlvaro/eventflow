import { expect, test } from '@playwright/test'

for (const width of [360, 768, 1280]) {
  test(`operator controls fit and remain keyboard reachable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 })
    await page.route('**/api/v1/session', (route) => route.fulfill({ json: {
      operator_id: 'operator-1', organization_id: 'tenant-1', username: 'operador', expires_at: '2030-01-01T00:00:00Z',
    } }))
    await page.route('**/api/v1/demo/scenarios', (route) => route.fulfill({ json: { items: [
      { id: 'success', event_type: 'demo.success', ready: true },
      { id: 'transient', event_type: 'demo.transient', ready: true },
      { id: 'rate-limit', event_type: 'demo.rate_limit', ready: true },
      { id: 'replay', event_type: 'demo.replay', ready: true },
    ] } }))
    await page.route('**/api/v1/management/metrics', (route) => route.fulfill({ json: {
      events: 4, deliveries: { succeeded: 2, pending: 1 }, attempts: { succeeded: 2 }, mean_attempt_duration_ms: 83,
    } }))
    await page.route('**/api/v1/management/events?*', (route) => route.fulfill({ json: { items: [], next_cursor: null } }))
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Del evento al webhook' })).toBeVisible()
    await expect(page.getByRole('button', { name: /Ejecutar escenario/ })).toHaveCount(4)
    const overflows = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
    expect(overflows).toBe(false)
    await page.keyboard.press('Tab')
    await expect(page.getByRole('button', { name: 'Salir' })).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(page.getByRole('button', { name: /Ejecutar escenario/ }).first()).toBeFocused()
  })
}
