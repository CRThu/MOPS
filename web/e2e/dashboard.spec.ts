import { test, expect } from '@playwright/test'
import { mockStatusEmpty, mockStatusWithServers } from './fixtures/mock-data'

test.describe('Dashboard', () => {
  test('loads with correct title and stats bar', async ({ page }) => {
    await page.route('**/api/dashboard', (route) =>
      route.fulfill({ json: mockStatusEmpty })
    )
    await page.goto('/')

    await expect(page).toHaveTitle('MOPS Dashboard')
    await expect(page.locator('.stats-bar')).toBeVisible()
    await expect(page.locator('#stat-traffic')).toHaveText('0 B ↑ 0 B ↓')
    await expect(page.locator('#stat-speed')).toHaveText('0 B/s ↑ 0 B/s ↓')
  })

  test('renders topology panel with mock data', async ({ page }) => {
    await page.route('**/api/dashboard', (route) =>
      route.fulfill({ json: mockStatusWithServers })
    )
    await page.goto('/')

    // Verify topology panel is present and visible
    const panel = page.locator('.topo-panel')
    await expect(panel).toBeVisible()

    // Container exists (G6 renders into it)
    await expect(page.locator('#topo-container')).toBeVisible()
  })

  test('renders server cards', async ({ page }) => {
    await page.route('**/api/dashboard', (route) =>
      route.fulfill({ json: mockStatusWithServers })
    )
    await page.goto('/')

    // Wait for poll cycle to complete
    await expect(page.locator('#cards-count')).toHaveText('2', { timeout: 10000 })

    // Should have server cards
    const cards = page.locator('.server-card')
    await expect(cards).toHaveCount(2)

    // First card should be active (sorted active first)
    await expect(cards.first().locator('.card-status')).toHaveText('ACTIVE')
  })

  test('shows empty state when no servers', async ({ page }) => {
    await page.route('**/api/dashboard', (route) =>
      route.fulfill({ json: mockStatusEmpty })
    )
    await page.goto('/')

    await expect(page.locator('#cards-list')).toContainText('Discovering servers...')
  })

  test('updates stats from API response', async ({ page }) => {
    await page.route('**/api/dashboard', (route) =>
      route.fulfill({ json: mockStatusWithServers })
    )
    await page.goto('/')

    await expect(page.locator('#stat-traffic')).toContainText('MB')
    await expect(page.locator('#stat-speed')).toContainText('B/s')
    await expect(page.locator('#stat-conns')).toHaveText('2')
  })

  test('renders header with uptime', async ({ page }) => {
    await page.route('**/api/dashboard', (route) =>
      route.fulfill({ json: mockStatusWithServers })
    )
    await page.goto('/')

    await expect(page.locator('#hdr-uptime')).toContainText('1d 0m')
    await expect(page.locator('#hdr-status')).toContainText('LIVE')
  })
})
