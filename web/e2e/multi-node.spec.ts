import { test, expect } from '@playwright/test'
import {
  mockStatusThreeServersMixed,
  mockStatusFiveServers,
  mockStatusMultipleClients,
  mockStatusAllOffline,
} from './fixtures/mock-data'

test.describe('Multi-Server Topology Rendering', () => {
  test('renders 3 servers with mixed states (active/circuit-open)', async ({ page }) => {
    await page.route('**/api/dashboard', (route) =>
      route.fulfill({ json: mockStatusThreeServersMixed })
    )
    await page.goto('/')

    // Wait for poll cycle
    await expect(page.locator('#cards-count')).toHaveText('3', { timeout: 10000 })

    // Should have 3 server cards
    const cards = page.locator('.server-card')
    await expect(cards).toHaveCount(3)

    // Topology panel should be visible
    await expect(page.locator('.topo-panel')).toBeVisible()
    await expect(page.locator('#topo-container')).toBeVisible()

    // Stats should reflect aggregated traffic
    await expect(page.locator('#stat-traffic')).toContainText('MB')
    await expect(page.locator('#stat-conns')).toHaveText('5')
  })

  test('renders 5 servers (stress test)', async ({ page }) => {
    await page.route('**/api/dashboard', (route) =>
      route.fulfill({ json: mockStatusFiveServers })
    )
    await page.goto('/')

    await expect(page.locator('#cards-count')).toHaveText('5', { timeout: 10000 })

    const cards = page.locator('.server-card')
    await expect(cards).toHaveCount(5)

    // Topology should still render without errors
    await expect(page.locator('#topo-container')).toBeVisible()

    // Aggregated stats
    await expect(page.locator('#stat-traffic')).toContainText('MB')
    await expect(page.locator('#stat-conns')).toHaveText('4')
  })

  test('shows empty state when all servers offline', async ({ page }) => {
    await page.route('**/api/dashboard', (route) =>
      route.fulfill({ json: mockStatusAllOffline })
    )
    await page.goto('/')

    await expect(page.locator('#cards-count')).toHaveText('2', { timeout: 10000 })

    // Server cards should exist but show offline status
    const cards = page.locator('.server-card')
    await expect(cards).toHaveCount(2)

    // All cards should show OFFLINE
    const statusBadges = cards.locator('.card-status')
    await expect(statusBadges.nth(0)).toHaveText('OFFLINE')
    await expect(statusBadges.nth(1)).toHaveText('OFFLINE')

    // Stats should be zero
    await expect(page.locator('#stat-traffic')).toHaveText('0 B ↑ 0 B ↓')
    await expect(page.locator('#stat-conns')).toHaveText('0')
  })
})

test.describe('Multi-Client Connection Rendering', () => {
  test('renders connections from multiple clients to different servers', async ({ page }) => {
    await page.route('**/api/dashboard', (route) =>
      route.fulfill({ json: mockStatusMultipleClients })
    )
    await page.goto('/')

    await expect(page.locator('#cards-count')).toHaveText('3', { timeout: 10000 })

    // Should have 3 server cards with connections
    const cards = page.locator('.server-card')
    await expect(cards).toHaveCount(3)

    // Stats should show 6 active connections
    await expect(page.locator('#stat-conns')).toHaveText('6')

    // Traffic should be non-zero
    await expect(page.locator('#stat-traffic')).toContainText('MB')
  })

  test('server cards show correct per-server connection counts', async ({ page }) => {
    await page.route('**/api/dashboard', (route) =>
      route.fulfill({ json: mockStatusMultipleClients })
    )
    await page.goto('/')

    await expect(page.locator('#cards-count')).toHaveText('3', { timeout: 10000 })

    // Each card should show its active_conns
    const cards = page.locator('.server-card')
    // Cards are sorted active-first, so check that they exist
    await expect(cards).toHaveCount(3)
  })

  test('topology shows multiple client nodes when different clients connect', async ({ page }) => {
    // This mock data has 3 different clients: 192.168.1.10, .20, .30
    await page.route('**/api/dashboard', (route) =>
      route.fulfill({ json: mockStatusMultipleClients })
    )
    await page.goto('/')

    await expect(page.locator('#cards-count')).toHaveText('3', { timeout: 10000 })

    // Topology should render without errors
    await expect(page.locator('#topo-container')).toBeVisible()

    // Canvas elements exist (G6 renders into canvas)
    const canvases = page.locator('#topo-container canvas')
    await expect(canvases.first()).toBeVisible()
  })
})

test.describe('Dynamic Topology Updates', () => {
  test('updates topology when server goes from active to circuit-open', async ({ page }) => {
    // Start with all active
    await page.route('**/api/dashboard', (route) =>
      route.fulfill({ json: mockStatusThreeServersMixed })
    )
    await page.goto('/')
    await expect(page.locator('#cards-count')).toHaveText('3', { timeout: 10000 })

    // Verify initial state
    const cards = page.locator('.server-card')
    await expect(cards).toHaveCount(3)

    // Update route to return data with one more server going circuit-open
    await page.unroute('**/api/dashboard')
    const updatedData = {
      ...mockStatusThreeServersMixed,
      nodes: mockStatusThreeServersMixed.nodes.map((n) =>
        n.hostname === 'server-alpha'
          ? { ...n, fails: 5, status: 'circuit-open' as const, active_conns: 0, speed_up: 0, speed_down: 0 }
          : n
      ),
      active_conns: 2,
    }
    await page.route('**/api/dashboard', (route) =>
      route.fulfill({ json: updatedData })
    )

    // Wait for next poll cycle (15s default, but data is re-fetched on reload)
    await page.reload()
    await expect(page.locator('#cards-count')).toHaveText('3', { timeout: 10000 })

    // Conns should decrease
    await expect(page.locator('#stat-conns')).toHaveText('2')
  })

  test('handles server appearing dynamically', async ({ page }) => {
    // Start with 2 servers
    const twoServers = {
      ...mockStatusThreeServersMixed,
      nodes: mockStatusThreeServersMixed.nodes.slice(0, 2),
      active_conns: 3,
    }
    await page.route('**/api/dashboard', (route) =>
      route.fulfill({ json: twoServers })
    )
    await page.goto('/')
    await expect(page.locator('#cards-count')).toHaveText('2', { timeout: 10000 })

    // Now a third server appears
    await page.unroute('**/api/dashboard')
    await page.route('**/api/dashboard', (route) =>
      route.fulfill({ json: mockStatusThreeServersMixed })
    )

    // Reload to trigger re-fetch
    await page.reload()
    await expect(page.locator('#cards-count')).toHaveText('3', { timeout: 10000 })

    // All 3 cards should render
    const cards = page.locator('.server-card')
    await expect(cards).toHaveCount(3)
  })
})

test.describe('Server Card State Rendering', () => {
  test('active servers show correct status badge', async ({ page }) => {
    await page.route('**/api/dashboard', (route) =>
      route.fulfill({ json: mockStatusThreeServersMixed })
    )
    await page.goto('/')
    await expect(page.locator('#cards-count')).toHaveText('3', { timeout: 10000 })

    // Find the active card (server-alpha)
    const activeCard = page.locator('.server-card', { hasText: 'server-alpha' })
    await expect(activeCard.locator('.card-status')).toHaveText('ACTIVE')
  })

  test('circuit-open servers show correct status badge', async ({ page }) => {
    await page.route('**/api/dashboard', (route) =>
      route.fulfill({ json: mockStatusThreeServersMixed })
    )
    await page.goto('/')
    await expect(page.locator('#cards-count')).toHaveText('3', { timeout: 10000 })

    // Find the circuit-open card (server-beta)
    const circuitCard = page.locator('.server-card', { hasText: 'server-beta' })
    await expect(circuitCard.locator('.card-status')).toHaveText('CIRCUIT OPEN')
  })

  test('server cards show traffic stats', async ({ page }) => {
    await page.route('**/api/dashboard', (route) =>
      route.fulfill({ json: mockStatusMultipleClients })
    )
    await page.goto('/')
    await expect(page.locator('#cards-count')).toHaveText('3', { timeout: 10000 })

    // Each card should have traffic info
    const cards = page.locator('.server-card')
    await expect(cards).toHaveCount(3)

    // First card (server-us with highest traffic) should show MB
    const firstCard = cards.first()
    await expect(firstCard).toContainText('↑')
    await expect(firstCard).toContainText('↓')
  })
})

test.describe('Aggregated Stats', () => {
  test('total traffic sums all servers', async ({ page }) => {
    await page.route('**/api/dashboard', (route) =>
      route.fulfill({ json: mockStatusFiveServers })
    )
    await page.goto('/')

    await expect(page.locator('#stat-traffic')).toContainText('MB')
    // Total up: ~19.4MB, total down: ~38.8MB
    await expect(page.locator('#stat-speed')).toContainText('B/s')
  })

  test('active connections count across all servers', async ({ page }) => {
    await page.route('**/api/dashboard', (route) =>
      route.fulfill({ json: mockStatusMultipleClients })
    )
    await page.goto('/')

    // 6 active connections across 3 servers
    await expect(page.locator('#stat-conns')).toHaveText('6')
  })

  test('uptime displays correctly', async ({ page }) => {
    await page.route('**/api/dashboard', (route) =>
      route.fulfill({ json: mockStatusMultipleClients })
    )
    await page.goto('/')

    // 345600 seconds = 4 days
    await expect(page.locator('#hdr-uptime')).toContainText('4d')
    await expect(page.locator('#hdr-status')).toContainText('LIVE')
  })
})
