import { expect, test } from '@playwright/test'
import { sampleAnalysis } from '../src/test/analysisSample'

/** One second of a 220 Hz tone as a 16-bit mono WAV, so the browser has real audio to decode. */
function wavFile(): Buffer {
  const sampleRate = 8000
  const data = Buffer.alloc(sampleRate * 2)
  for (let i = 0; i < sampleRate; i++) data.writeInt16LE(Math.round(8000 * Math.sin((2 * Math.PI * 220 * i) / sampleRate)), i * 2)
  const header = Buffer.alloc(44)
  header.write('RIFF', 0)
  header.writeUInt32LE(36 + data.length, 4)
  header.write('WAVEfmt ', 8)
  header.writeUInt32LE(16, 16)
  header.writeUInt16LE(1, 20)
  header.writeUInt16LE(1, 22)
  header.writeUInt32LE(sampleRate, 24)
  header.writeUInt32LE(sampleRate * 2, 28)
  header.writeUInt16LE(2, 32)
  header.writeUInt16LE(16, 34)
  header.write('data', 36)
  header.writeUInt32LE(data.length, 40)
  return Buffer.concat([header, data])
}

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

test('workspace rejects a non-audio file', async ({ page }) => {
  await page.goto('/workspace')
  const input = page.getByLabel(/^Audio file/)

  await input.setInputFiles({ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('hello') })
  await expect(page.getByRole('alert')).toContainText('is not a supported audio file')
})

test('primary navigation is reachable by keyboard with a visible skip link', async ({ page }) => {
  await page.goto('/')
  // Wait until the page has rendered; pressing Tab on a still-empty page focuses nothing.
  await expect(page.getByRole('link', { name: 'Skip to main content' })).toBeAttached()
  await page.keyboard.press('Tab')

  await expect(page.getByRole('link', { name: 'Skip to main content' })).toBeFocused()
  await expect(page.getByRole('link', { name: 'Skip to main content' })).toBeInViewport()
})

test('uploads a recording, shows the backend result, and carries it to the dashboard and Acoustic Twin', async ({ page }) => {
  // The backend is mocked here; this checks the browser flow, not the analysis itself.
  let uploadedName = ''
  await page.route('**/api/analyze', async (route) => {
    uploadedName = /filename="([^"]+)"/.exec(route.request().postData() ?? '')?.[1] ?? ''
    await route.fulfill({ json: sampleAnalysis() })
  })

  await page.goto('/workspace')
  await page.getByLabel(/^Audio file/).setInputFiles({ name: 'talk.wav', mimeType: 'audio/wav', buffer: wavFile() })
  await expect(page.getByText('Duration 0:01.0')).toBeVisible()
  await page.getByLabel('The text you were delivering').fill('Good morning everyone. Thank you coming')
  await page.getByRole('button', { name: 'Run analysis' }).click()

  const result = page.getByRole('region', { name: 'Analysis complete' })
  await expect(result.getByText('good morning everyone thanks for coming')).toBeVisible()
  await expect(result.getByText('0:00.1–0:00.4')).toBeVisible()
  expect(uploadedName).toBe('talk.wav')

  await result.getByRole('link', { name: 'Open the dashboard' }).click()
  await expect(page.getByText('Real analysis · talk.wav')).toBeVisible()
  await expect(page.getByText('Demo data — not a real analysis')).toHaveCount(0)
  await expect(page.getByText('Analysis complete, with findings')).toBeVisible()
  await expect(page.getByRole('list', { name: 'Findings' }).getByRole('heading', { name: 'Longer pause than the reference' })).toBeVisible()

  await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Acoustic Twin' }).click()
  await expect(page.getByText('Real analysis · talk.wav')).toBeVisible()
  await page.getByRole('button', { name: '2D view' }).click()
  await expect(page.getByRole('img', { name: /Measured from talk.wav/ })).toBeVisible()
})

test('explains that the backend is unreachable when the request fails', async ({ page }) => {
  await page.route('**/api/analyze', (route) => route.abort('connectionrefused'))

  await page.goto('/workspace')
  await page.getByLabel(/^Audio file/).setInputFiles({ name: 'talk.wav', mimeType: 'audio/wav', buffer: wavFile() })
  await page.getByRole('button', { name: 'Run analysis' }).click()

  await expect(page.getByRole('alert')).toContainText('Can’t reach the analysis backend')
})
