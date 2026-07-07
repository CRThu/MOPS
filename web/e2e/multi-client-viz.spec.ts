import { test, expect } from '@playwright/test'
import { mockStatusMultipleClients, mockStatusStandalone, mockStatusStandaloneWithConns, mockStatusLargeScale } from './fixtures/mock-data'

test.describe('Multi-Client Topology Visualization', () => {
  test('renders 3 clients connecting to different servers', async ({ page }) => {
    await page.route('**/api/dashboard', (route) =>
      route.fulfill({ json: mockStatusMultipleClients })
    )
    await page.goto('/')

    await expect(page.locator('#cards-count')).toHaveText('3', { timeout: 10000 })
    await expect(page.locator('#topo-container')).toBeVisible()
    await page.screenshot({ path: 'e2e/multi-client-topology-test.png', fullPage: false })
    await expect(page.locator('#stat-conns')).toHaveText('6')
    await expect(page.locator('#stat-traffic')).toContainText('MB')
  })

  test('topology shows correct client count in title', async ({ page }) => {
    await page.route('**/api/dashboard', (route) =>
      route.fulfill({ json: mockStatusMultipleClients })
    )
    await page.goto('/')

    await expect(page.locator('#cards-count')).toHaveText('3', { timeout: 10000 })
    await expect(page.locator('#cards-count')).toHaveText('3')
  })

  test('standalone dashboard shows servers without App node', async ({ page }) => {
    await page.route('**/api/dashboard', (route) =>
      route.fulfill({ json: mockStatusStandalone })
    )
    await page.goto('/')

    await expect(page.locator('#cards-count')).toHaveText('2', { timeout: 10000 })
    await expect(page.locator('#topo-container')).toBeVisible()
    await page.screenshot({ path: 'e2e/standalone-topology.png', fullPage: false })
    await expect(page.locator('#stat-conns')).toHaveText('5')
  })

  test('standalone with connections infers clients', async ({ page }) => {
    await page.route('**/api/dashboard', (route) =>
      route.fulfill({ json: mockStatusStandaloneWithConns })
    )
    await page.goto('/')

    await expect(page.locator('#cards-count')).toHaveText('2', { timeout: 10000 })
    await expect(page.locator('#topo-container')).toBeVisible()
    await page.screenshot({ path: 'e2e/standalone-with-conns.png', fullPage: false })
  })

  test('large scale topology renders correctly', async ({ page }) => {
    await page.route('**/api/dashboard', (route) =>
      route.fulfill({ json: mockStatusLargeScale })
    )
    await page.goto('/')

    await expect(page.locator('#cards-count')).toHaveText('5', { timeout: 10000 })
    await expect(page.locator('#topo-container')).toBeVisible()
    await page.screenshot({ path: 'e2e/large-scale-topology.png', fullPage: false })
    await expect(page.locator('#stat-conns')).toHaveText('10')
  })
})
