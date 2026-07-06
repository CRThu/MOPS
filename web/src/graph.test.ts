import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createGraph, updateGraph } from './topo'
import type { TopoData } from './types'

// Mock @antv/g6
const { MockGraph, mockGraphInstance } = vi.hoisted(() => {
  const instance = {
    setData: vi.fn(),
    render: vi.fn(),
    fitView: vi.fn(),
    getNodes: vi.fn(() => []),
    on: vi.fn(),
  }
  class Graph {
    constructor(_opts: any) {}
    setData = instance.setData
    render = instance.render
    fitView = instance.fitView
    getNodes = instance.getNodes
    on = instance.on
  }
  return { MockGraph: Graph, mockGraphInstance: instance }
})

vi.mock('@antv/g6', () => ({
  Graph: MockGraph,
}))

function makeTopoData(overrides: Partial<TopoData> = {}): TopoData {
  return {
    nodes: [
      { id: 'app', type: 'app', label: 'App' },
      { id: 'cli-local', type: 'client', label: 'Client' },
      { id: 'srv-10.0.0.1:10080', type: 'server', label: 'server-a' },
      { id: 'inet', type: 'internet', label: 'Internet' },
    ],
    edges: [
      { id: 'e-app-cli', source: 'app', target: 'cli-local', isActive: true },
      { id: 'e-cli-srv', source: 'cli-local', target: 'srv-10.0.0.1:10080', isActive: false },
      { id: 'e-srv-inet', source: 'srv-10.0.0.1:10080', target: 'inet', isActive: true },
    ],
    ...overrides,
  }
}

describe('createGraph', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns a Graph instance', () => {
    const container = document.createElement('div')
    const graph = createGraph(container)
    expect(graph).toBeDefined()
    expect(graph.setData).toBeDefined()
    expect(graph.render).toBeDefined()
  })
})

describe('updateGraph', () => {
  let graph: ReturnType<typeof createGraph>

  beforeEach(() => {
    vi.clearAllMocks()
    const container = document.createElement('div')
    graph = createGraph(container)
  })

  it('calls setData with rect nodes and correct data', async () => {
    const data = makeTopoData()
    await updateGraph(graph, data)

    expect(graph.setData).toHaveBeenCalledWith(
      expect.objectContaining({
        nodes: expect.arrayContaining([
          expect.objectContaining({ id: 'app', type: 'rect' }),
          expect.objectContaining({ id: 'cli-local', type: 'rect' }),
          expect.objectContaining({ id: 'srv-10.0.0.1:10080', type: 'rect' }),
          expect.objectContaining({ id: 'inet', type: 'rect' }),
        ]),
        edges: expect.arrayContaining([
          expect.objectContaining({ id: 'e-app-cli', source: 'app', target: 'cli-local' }),
        ]),
      })
    )
  })

  it('calls render and fitView', async () => {
    await updateGraph(graph, makeTopoData())
    expect(graph.render).toHaveBeenCalled()
    expect(graph.fitView).toHaveBeenCalled()
  })

  it('applies active edge styles', async () => {
    const data = makeTopoData({
      edges: [
        { id: 'e-active', source: 'app', target: 'cli-local', isActive: true },
      ],
    })
    await updateGraph(graph, data)

    const edgesArg = graph.setData.mock.calls[0][0].edges
    const activeEdge = edgesArg.find((e: any) => e.id === 'e-active')
    expect(activeEdge.style.stroke).toBe('#2d6a4f')
    expect(activeEdge.style.lineWidth).toBe(2)
    expect(activeEdge.style.lineDash).toBeUndefined()
  })

  it('applies inactive edge styles', async () => {
    const data = makeTopoData({
      edges: [
        { id: 'e-inactive', source: 'cli-local', target: 'srv-10.0.0.1:10080', isActive: false },
      ],
    })
    await updateGraph(graph, data)

    const edgesArg = graph.setData.mock.calls[0][0].edges
    const inactiveEdge = edgesArg.find((e: any) => e.id === 'e-inactive')
    expect(inactiveEdge.style.stroke).toBe('#374151')
    expect(inactiveEdge.style.lineWidth).toBe(1)
    expect(inactiveEdge.style.lineDash).toEqual([4, 3])
  })

  it('applies correct node colors by type', async () => {
    const data = makeTopoData()
    await updateGraph(graph, data)

    const nodesArg = graph.setData.mock.calls[0][0].nodes
    const appNode = nodesArg.find((n: any) => n.id === 'app')
    const clientNode = nodesArg.find((n: any) => n.id === 'cli-local')
    const serverNode = nodesArg.find((n: any) => n.id === 'srv-10.0.0.1:10080')
    const inetNode = nodesArg.find((n: any) => n.id === 'inet')

    expect(appNode.style.fill).toBe('#374151')
    expect(clientNode.style.fill).toBe('#1e3a5f')
    expect(serverNode.style.fill).toBe('#1a3c2a')
    expect(inetNode.style.fill).toBe('#2d1b4e')
  })

  it('applies offline node color', async () => {
    const data = makeTopoData({
      nodes: [
        { id: 'app', type: 'app', label: 'App' },
        { id: 'srv-10.0.0.2:10080', type: 'offline', label: 'server-b' },
        { id: 'inet', type: 'internet', label: 'Internet' },
      ],
    })
    await updateGraph(graph, data)

    const nodesArg = graph.setData.mock.calls[0][0].nodes
    const offlineNode = nodesArg.find((n: any) => n.id === 'srv-10.0.0.2:10080')
    expect(offlineNode.style.fill).toBe('#1f2937')
  })
})
