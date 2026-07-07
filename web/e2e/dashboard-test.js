/**
 * MOPS Dashboard DevTools Test Script
 * Tests topology rendering with multiple servers and clients
 */

// Test data: 3 servers + 3 clients with mixed states
const testStatus = {
  nodes: [
    { ip: '10.0.0.1', port: 10080, api_port: 10082, hostname: 'server-us', fails: 0, status: 'active', total_up: 5242880, total_down: 10485760, active_conns: 3, connections: [], speed_up: 4096, speed_down: 8192 },
    { ip: '10.0.0.2', port: 10080, api_port: 10083, hostname: 'server-eu', fails: 0, status: 'active', total_up: 2097152, total_down: 4194304, active_conns: 2, connections: [], speed_up: 2048, speed_down: 4096 },
    { ip: '10.0.0.3', port: 10080, api_port: 10084, hostname: 'server-ap', fails: 0, status: 'active', total_up: 1048576, total_down: 2097152, active_conns: 1, connections: [], speed_up: 1024, speed_down: 2048 },
  ],
  connections: [
    // Client A: Carrot-PC connecting to US and EU servers
    { conn_id: 'c1', client_ip: '192.168.1.10', client_port: 10090, client_host: 'Carrot-PC', target_host: 'amazon.com', target_port: 443, status: 'active', started_at: Date.now() / 1000 - 200, server_node: '10.0.0.1:10080' },
    { conn_id: 'c2', client_ip: '192.168.1.10', client_port: 10090, client_host: 'Carrot-PC', target_host: 'google.com', target_port: 443, status: 'active', started_at: Date.now() / 1000 - 150, server_node: '10.0.0.2:10080' },
    { conn_id: 'c3', client_ip: '192.168.1.10', client_port: 10090, client_host: 'Carrot-PC', target_host: 'youtube.com', target_port: 443, status: 'active', started_at: Date.now() / 1000 - 100, server_node: '10.0.0.1:10080' },
    // Client B: Workstation connecting to US and AP servers
    { conn_id: 'c4', client_ip: '192.168.1.20', client_port: 10091, client_host: 'Workstation', target_host: 'twitter.com', target_port: 443, status: 'active', started_at: Date.now() / 1000 - 80, server_node: '10.0.0.1:10080' },
    { conn_id: 'c5', client_ip: '192.168.1.20', client_port: 10091, client_host: 'Workstation', target_host: 'Line.me', target_port: 443, status: 'active', started_at: Date.now() / 1000 - 50, server_node: '10.0.0.3:10080' },
    // Client C: Laptop connecting to EU server
    { conn_id: 'c6', client_ip: '192.168.1.30', client_port: 10092, client_host: 'Laptop', target_host: 'spotify.com', target_port: 443, status: 'active', started_at: Date.now() / 1000 - 30, server_node: '10.0.0.2:10080' },
    // Completed connections
    { conn_id: 'c7', client_ip: '192.168.1.10', client_port: 10090, client_host: 'Carrot-PC', target_host: 'github.com', target_port: 443, status: 'completed', started_at: Date.now() / 1000 - 500, ended_at: Date.now() / 1000 - 200, server_node: '10.0.0.1:10080' },
    { conn_id: 'c8', client_ip: '192.168.1.30', client_port: 10092, client_host: 'Laptop', target_host: 'stackoverflow.com', target_port: 443, status: 'completed', started_at: Date.now() / 1000 - 400, ended_at: Date.now() / 1000 - 100, server_node: '10.0.0.2:10080' },
  ],
  total_up: 8388608,
  total_down: 16777216,
  speed_up: 7168,
  speed_down: 14336,
  active_conns: 6,
  uptime: 345600,
  mode: 'dashboard',
  strategy: 'mDNS',
  local_client: null,
}

// Helper function to check if an element exists
function elementExists(selector) {
  return document.querySelector(selector) !== null
}

// Helper function to get element text
function getElementText(selector) {
  const el = document.querySelector(selector)
  return el ? el.textContent : null
}

// Helper function to count elements
function countElements(selector) {
  return document.querySelectorAll(selector).length
}

// Run the test
console.log('=== MOPS Dashboard DevTools Test ===')
console.log('Test data: 3 servers + 3 clients')
console.log('')

// Check if we're on the dashboard page
const title = document.title
console.log(`Page title: ${title}`)

// Check for graph container
const graphContainer = document.querySelector('#graph-container') || document.querySelector('[class*="graph"]') || document.querySelector('canvas')
if (graphContainer) {
  console.log('✓ Graph container found')
} else {
  console.log('✗ Graph container not found')
}

// Check for any SVG or canvas elements (G6 renders to canvas)
const canvasElements = document.querySelectorAll('canvas')
const svgElements = document.querySelectorAll('svg')
console.log(`Canvas elements: ${canvasElements.length}`)
console.log(`SVG elements: ${svgElements.length}`)

// Check for any text content that might indicate nodes
const allText = document.body.innerText
const hasServerUs = allText.includes('server-us')
const hasServerEu = allText.includes('server-eu')
const hasServerAp = allText.includes('server-ap')
const hasCarrotPc = allText.includes('Carrot-PC')
const hasWorkstation = allText.includes('Workstation')
const hasLaptop = allText.includes('Laptop')

console.log('')
console.log('=== Node Label Detection ===')
console.log(`Server US: ${hasServerUs ? '✓' : '✗'}`)
console.log(`Server EU: ${hasServerEu ? '✓' : '✗'}`)
console.log(`Server AP: ${hasServerAp ? '✓' : '✗'}`)
console.log(`Client Carrot-PC: ${hasCarrotPc ? '✓' : '✗'}`)
console.log(`Client Workstation: ${hasWorkstation ? '✓' : '✗'}`)
console.log(`Client Laptop: ${hasLaptop ? '✓' : '✗'}`)

// Check for any error messages
const errorElements = document.querySelectorAll('[class*="error"], [class*="Error"]')
console.log('')
console.log(`Error elements: ${errorElements.length}`)

// Check for console errors
console.log('')
console.log('=== Test Summary ===')
const passed = (hasServerUs && hasServerEu && hasServerAp && hasCarrotPc && hasWorkstation && hasLaptop)
console.log(`Test ${passed ? 'PASSED' : 'FAILED'}`)

// Return test result
return {
  passed,
  details: {
    hasServerUs,
    hasServerEu,
    hasServerAp,
    hasCarrotPc,
    hasWorkstation,
    hasLaptop,
    canvasCount: canvasElements.length,
    svgCount: svgElements.length,
    errorCount: errorElements.length,
  }
}
