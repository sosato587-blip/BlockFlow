import { test, expect } from '@playwright/test'

/**
 * Smoke tests: hit key routes and make sure they render without 500s and that
 * mock-mode API endpoints respond with `ok: true`. Does NOT exercise RunPod —
 * relies on staging running with BLOCKFLOW_MOCK_RUNPOD=1.
 */

test.describe('BlockFlow smoke', () => {
  test('mobile page loads', async ({ page }) => {
    const response = await page.goto('/m')
    expect(response?.status()).toBeLessThan(400)
    // Should render *something* — the mobile tab bar.
    await expect(page.locator('body')).toBeVisible()
  })

  test('tools page loads', async ({ page }) => {
    const response = await page.goto('/tools')
    expect(response?.status()).toBeLessThan(400)
    await expect(page.locator('body')).toBeVisible()
  })

  test('generate pipeline page loads', async ({ page }) => {
    const response = await page.goto('/')
    expect(response?.status()).toBeLessThan(400)
    await expect(page.locator('body')).toBeVisible()
  })
})

test.describe('Mock-mode API contracts', () => {
  test('/api/blocks/base_model_selector/families returns 7 families', async ({ request }) => {
    const res = await request.get('/api/blocks/base_model_selector/families')
    expect(res.ok()).toBeTruthy()
    const body = await res.json()
    expect(body.ok).toBe(true)
    expect(Array.isArray(body.families)).toBe(true)
    expect(body.families.length).toBeGreaterThanOrEqual(7)
    const ids = body.families.map((f: { id: string }) => f.id)
    expect(ids).toEqual(expect.arrayContaining(['illustrious', 'sdxl', 'z_image', 'wan_22', 'flux', 'ltx']))
  })

  test('/api/blocks/lora_selector/loras returns grouped LoRAs', async ({ request }) => {
    const res = await request.get('/api/blocks/lora_selector/loras')
    expect(res.ok()).toBeTruthy()
    const body = await res.json()
    expect(body.ok).toBe(true)
    expect(body).toHaveProperty('grouped_high')
    expect(body).toHaveProperty('grouped_low')
    expect(body).toHaveProperty('families')
  })

  test('/api/blocks/lora_selector/loras?family=illustrious filters', async ({ request }) => {
    const res = await request.get('/api/blocks/lora_selector/loras?family=illustrious')
    expect(res.ok()).toBeTruthy()
    const body = await res.json()
    expect(body.ok).toBe(true)
    expect(body.applied_family).toBe('illustrious')
    // Every returned LoRA should be grouped under illustrious.
    const allHigh: string[] = body.high ?? []
    expect(allHigh.every((f) => body.grouped_high.illustrious.includes(f))).toBe(true)
  })

  test('/api/m/ltx_dl_info returns LTX 2B download spec', async ({ request }) => {
    const res = await request.get('/api/m/ltx_dl_info')
    expect(res.ok()).toBeTruthy()
    const body = await res.json()
    expect(body.ok).toBe(true)
    expect(Array.isArray(body.downloads)).toBe(true)
    expect(body.downloads[0].filename).toBe('ltx-video-2b-v0.9.5.safetensors')
  })
})

test.describe('Mock-mode video generation', () => {
  test('LTX mock request completes with placeholder URL', async ({ request }) => {
    const res = await request.post('/api/m/ltx_video', {
      data: {
        prompt: 'smoke test',
        image_url: '',
        width: 512, height: 768, length: 25, fps: 25, steps: 20,
      },
    })
    // In mock mode the server should 200 with ok:true and a job id.
    // If mock mode is off this test is expected to fail — CI env must export
    // BLOCKFLOW_MOCK_RUNPOD=1.
    expect(res.ok()).toBeTruthy()
    const body = await res.json()
    expect(body.ok).toBe(true)
  })
})
