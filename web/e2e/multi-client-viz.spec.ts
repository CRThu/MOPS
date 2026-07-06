import { test, expect } from '@playwright/test'
import { mockStatusMultipleClients } from './fixtures/mock-data'

test.describe('Multi-Client Topology Visualization', () => {
  test('renders 3 clients connecting to different servers', async ({ page }) => {
    // This mock has 3 clients: 192.168.1.10, .20, .30
    // Client A -> server-us, server-eu
    // Client B -> server-us, server-ap
    // Client C -> server-eu only
    await page.route('**/api/dashboard', (route) =>
      route.fulfill({ json: mockStatusMultipleClients })
    )
    await page.goto('/')

    // Wait for data to load
    await expect(page.locator('#cards-count')).toHaveText('3', { timeout: 10000 })

    // Verify topology container is visible
    await expect(page.locator('#topo-container')).toBeVisible()

    // Take screenshot for visual verification
    await page.screenshot({ path: 'e2e/multi-client-topology-test.png', fullPage: false })

    // Verify stats show aggregated data
    await expect(page.locator('#stat-conns')).toHaveText('6')
    await expect(page.locator('#stat-traffic')).toContainText('MB')
  })

  test('topology shows correct client count in title', async ({ page }) => {
    await page.route('**/api/dashboard', (route) =>
      route.fulfill({ json: mockStatusMultipleClients })
    )
    await page.goto('/')

    await expect(page.locator('#cards-count')).toHaveText('3', { timeout: 10000 })

    // Server status header should show count
    await expect(page.locator('#cards-count')).toHaveText('3')
  })
})
