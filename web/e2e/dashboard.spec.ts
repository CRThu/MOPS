import { test, expect } from '@playwright/test'
import { mockStatusEmpty, mockStatusWithServers } from './fixtures/mock-data'

test.describe('Dashboard', () => {
  test('loads with correct title and stats bar', async ({ page }) => {
    await page.route('**/api/server', (route) =>
      route.fulfill({ json: mockStatusEmpty })
    )
    await page.goto('/')

    await expect(page).toHaveTitle('MOPS Dashboard')
    await expect(page.locator('.stats-bar')).toBeVisible()
    await expect(page.locator('#s-up')).toHaveText('0 B')
    await expect(page.locator('#s-down')).toHaveText('0 B')
  })

  test('renders topology panel with mock data', async ({ page }) => {
    await page.route('**/api/server', (route) =>
      route.fulfill({ json: mockStatusWithServers })
    )
    await page.goto('/')

    // Verify topology panel is present and visible
    const panel = page.locator('.topology-panel')
    await expect(panel).toBeVisible()
    await expect(panel.locator('.panel-header')).toHaveText('Network Topology')

    // Container exists (G6 renders into it)
    await expect(page.locator('#topo-container')).toBeVisible()
  })

  test('renders connection list', async ({ page }) => {
    await page.route('**/api/server', (route) =>
      route.fulfill({ json: mockStatusWithServers })
    )
    await page.goto('/')

    // Connection count badge should show 2
    await expect(page.locator('#conn-count')).toHaveText('2')

    // Should have connection cards
    const cards = page.locator('.conn-card')
    await expect(cards).toHaveCount(2)

    // First card should be active (sorted active first)
    await expect(cards.first().locator('.conn-status')).toHaveText('active')
  })

  test('renders traffic table', async ({ page }) => {
    await page.route('**/api/server', (route) =>
      route.fulfill({ json: mockStatusWithServers })
    )
    await page.goto('/')

    const table = page.locator('#traffic-table')
    await expect(table.locator('table')).toBeVisible()

    // Should have 2 server rows
    const rows = table.locator('tbody tr')
    await expect(rows).toHaveCount(2)

    // Total row should show combined traffic
    await expect(table.locator('.tr-total')).toContainText('Total')
  })

  test('shows empty state when no connections', async ({ page }) => {
    await page.route('**/api/server', (route) =>
      route.fulfill({ json: mockStatusEmpty })
    )
    await page.goto('/')

    await expect(page.locator('#conn-list')).toContainText('Waiting for connections…')
    await expect(page.locator('#traffic-table')).toContainText('No traffic yet')
  })

  test('updates stats from API response', async ({ page }) => {
    await page.route('**/api/server', (route) =>
      route.fulfill({ json: mockStatusWithServers })
    )
    await page.goto('/')

    await expect(page.locator('#s-up')).toContainText('MB')
    await expect(page.locator('#s-down')).toContainText('MB')
    await expect(page.locator('#s-active')).toHaveText('2')
    await expect(page.locator('#s-total')).toHaveText('2')
  })
})
