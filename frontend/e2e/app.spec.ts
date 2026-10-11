import { expect, test } from '@playwright/test'

test('navigates from the landing page to the demo dashboard', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('link', { name: 'Explore the demo analysis' }).click()

  await expect(page.getByRole('heading', { level: 1, name: 'Analysis' })).toBeVisible()
  await expect(page.getByText('Demo data — not a real analysis')).toBeVisible()
  await page.getByRole('button', { name: /^Flat pitch, / }).click()
  await expect(page.getByRole('region', { name: 'Selected finding' }).getByRole('heading', { name: 'Flat pitch' })).toBeVisible()
})

test('Acoustic Twin draws the 3D scene when WebGL works, and the 2D view on request', async ({ page }, testInfo) => {
  await page.goto('/twin')
  const webgl = await page.evaluate(() => {
    const canvas = document.createElement('canvas')
    return Boolean(canvas.getContext('webgl2') ?? canvas.getContext('webgl'))
  })
  test.skip(!webgl, 'This browser has no WebGL; the fallback is covered by the unit tests.')

  const canvas = page.locator('canvas')
  await expect(canvas).toBeVisible()
  // React Three Fiber only sizes the canvas once the renderer is running.
  await expect.poll(async () => Number(await canvas.getAttribute('width'))).toBeGreaterThan(0)
  await page.waitForTimeout(500)
  await page.screenshot({ path: testInfo.outputPath('twin-3d.png') })

  // A blank canvas compresses to almost nothing; a drawn scene does not.
  const drawn = await canvas.screenshot()
  expect(drawn.byteLength).toBeGreaterThan(15_000)

  await page.getByRole('button', { name: '2D view' }).click()
  await expect(page.getByRole('img', { name: /2D Acoustic Twin/ })).toBeVisible()
  await expect(canvas).toHaveCount(0)
})

test('Acoustic Twin falls back to 2D when WebGL is unavailable', async ({ page }) => {
  await page.addInitScript(() => {
    HTMLCanvasElement.prototype.getContext = () => null
  })
  await page.goto('/twin')

  await expect(page.getByText(/WebGL is not available in this browser/)).toBeVisible()
  await expect(page.getByRole('img', { name: /2D Acoustic Twin/ })).toBeVisible()
  await expect(page.getByRole('button', { name: '3D view' })).toBeDisabled()
})

test('workspace rejects a non-audio file and explains that analysis is not available', async ({ page }) => {
  await page.goto('/workspace')
  const input = page.getByLabel(/^Audio file/)

  await input.setInputFiles({ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('hello') })
  await expect(page.getByRole('alert')).toContainText('is not a supported audio file')
})

test('primary navigation is reachable by keyboard with a visible skip link', async ({ page }) => {
  await page.goto('/')
  await page.keyboard.press('Tab')

  await expect(page.getByRole('link', { name: 'Skip to main content' })).toBeFocused()
  await expect(page.getByRole('link', { name: 'Skip to main content' })).toBeInViewport()
})
