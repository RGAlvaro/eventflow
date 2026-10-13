import { expect, test } from '@playwright/test'

test('browser publishes, observes signed retries and replays through the real API', async ({
  page,
}) => {
  await page.goto('/')
  await page.getByLabel('Usuario').fill('browser-operator')
  await page.getByLabel('Contraseña').fill('browser-password')
  await page.getByRole('button', { name: 'Entrar a la consola' }).click()
  await expect(page.getByRole('heading', { name: 'Del evento al webhook' })).toBeVisible()
  await expect(page.getByText('Preparado')).toHaveCount(4)

  await page
    .getByRole('button', { name: /Ejecutar escenario/ })
    .nth(0)
    .click()
  await expect(page.locator('#delivery-detail .status')).toHaveText('succeeded', {
    timeout: 20_000,
  })
  await expect(page.getByText(/firma verificada/)).toBeVisible()

  await page
    .getByRole('button', { name: /Ejecutar escenario/ })
    .nth(1)
    .click()
  await expect(page.locator('#delivery-detail .status')).toHaveText('succeeded', {
    timeout: 25_000,
  })
  await expect(page.getByText('Intento 3 · generación 1')).toBeVisible()

  await page
    .getByRole('button', { name: /Ejecutar escenario/ })
    .nth(2)
    .click()
  await expect(page.locator('#delivery-detail .status')).toHaveText('succeeded', {
    timeout: 25_000,
  })
  await expect(page.getByText('Intento 2 · generación 1')).toBeVisible()

  await page
    .getByRole('button', { name: /Ejecutar escenario/ })
    .nth(3)
    .click()
  await expect(page.locator('#delivery-detail .status')).toHaveText('dead lettered', {
    timeout: 35_000,
  })
  await page.getByRole('button', { name: 'Reproducir entrega' }).click()
  await expect(page.locator('#delivery-detail .status')).toHaveText('succeeded', {
    timeout: 25_000,
  })
  await expect(page.getByText(/Generación 2: firma verificada/)).toBeVisible()
})
