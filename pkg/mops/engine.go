package mops

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"strconv"
	"sync"
	"sync/atomic"
	"time"
)

// Header defines the tunnel handshake protocol header.
type Header struct {
	Version    int    `json:"version"`
	Host       string `json:"host"`
	ClientPort int    `json:"client_port,omitempty"`
	ClientHost string `json:"client_host,omitempty"`
}

// Node represents a cluster proxy server node.
type Node struct {
	ID         string    `json:"id"`
	Hostname   string    `json:"hostname"`
	IP         string    `json:"ip"`
	Port       int       `json:"port"`
	Role       string    `json:"role"`
	Status     string    `json:"status"`
	ActiveConn int64     `json:"active_conns"`
	BytesUp    uint64    `json:"bytes_up"`
	BytesDown  uint64    `json:"bytes_down"`
	LastSeen   time.Time `json:"last_seen"`
	IsMe       bool      `json:"is_me"`
}

// Config defines the configuration for MOPS Engine.
type Config struct {
	ServerPort int
	ClientPort int
	ListenAddr string
	Hostname   string
	Advertise  string
	Strategy   string // "random" or "hash"
}

// Engine coordinates the proxy server, client, and node pool.
type Engine struct {
	cfg Config
	mu  sync.RWMutex

	nodes map[string]*Node

	serverListener net.Listener
	clientListener net.Listener

	running bool
	cancel  context.CancelFunc

	rrIndex uint64 // Round-Robin counter

	// Traffic stats
	bytesUp   uint64
	bytesDown uint64

	// Real-time speed calculation
	speedUp   float64
	speedDown float64
	lastUp    uint64
	lastDown  uint64
	lastCalc  time.Time
}

// NewEngine creates a new proxy Engine instance.
func NewEngine(cfg Config) *Engine {
	if cfg.ListenAddr == "" {
		cfg.ListenAddr = "127.0.0.1"
	}
	if cfg.Strategy == "" {
		cfg.Strategy = "random"
	}
	return &Engine{
		cfg:      cfg,
		nodes:    make(map[string]*Node),
		lastCalc: time.Now(),
	}
}

// Start launches the Server and Client listeners.
func (e *Engine) Start(ctx context.Context) error {
	e.mu.Lock()
	if e.running {
		e.mu.Unlock()
		return fmt.Errorf("engine already running")
	}

	ctx, cancel := context.WithCancel(ctx)
	e.cancel = cancel
	e.running = true

	// Add self node
	selfIP := e.cfg.Advertise
	if selfIP == "" || selfIP == "127.0.0.1" {
		if autoIP, err := GetOutboundIP(); err == nil && autoIP != "" {
			selfIP = autoIP
			e.cfg.Advertise = autoIP
		}
	}
	selfID := fmt.Sprintf("%s@%s:%d", e.cfg.Hostname, selfIP, e.cfg.ServerPort)
	selfNode := &Node{
		ID:       selfID,
		Hostname: e.cfg.Hostname,
		IP:       selfIP,
		Port:     e.cfg.ServerPort,
		Role:     "Both",
		Status:   "ONLINE",
		LastSeen: time.Now(),
		IsMe:     true,
	}
	e.nodes[selfID] = selfNode
	e.mu.Unlock()

	// Start Server
	if e.cfg.ServerPort > 0 {
		srvAddr := fmt.Sprintf("0.0.0.0:%d", e.cfg.ServerPort)
		l, err := net.Listen("tcp", srvAddr)
		if err != nil {
			return fmt.Errorf("failed to start server listener on %s: %w", srvAddr, err)
		}
		e.serverListener = l
		go e.acceptServer(l)
	}

	// Start Client (SOCKS5 Proxy)
	if e.cfg.ClientPort > 0 {
		cliAddr := fmt.Sprintf("%s:%d", e.cfg.ListenAddr, e.cfg.ClientPort)
		l, err := net.Listen("tcp", cliAddr)
		if err != nil {
			if e.serverListener != nil {
				e.serverListener.Close()
			}
			return fmt.Errorf("failed to start client listener on %s: %w", cliAddr, err)
		}
		e.clientListener = l
		go e.acceptClient(l)
	}

	// Speed calculation loop
	go e.speedLoop(ctx)

	return nil
}

// Stop gracefully stops the engine.
func (e *Engine) Stop() {
	e.mu.Lock()
	defer e.mu.Unlock()

	if !e.running {
		return
	}
	e.running = false
	if e.cancel != nil {
		e.cancel()
	}

	if e.serverListener != nil {
		e.serverListener.Close()
	}
	if e.clientListener != nil {
		e.clientListener.Close()
	}
}

// UpdateNode adds or updates a remote node in the pool.
func (e *Engine) UpdateNode(node *Node) {
	e.mu.Lock()
	defer e.mu.Unlock()

	if existing, ok := e.nodes[node.ID]; ok {
		existing.Hostname = node.Hostname
		existing.IP = node.IP
		existing.Port = node.Port
		existing.Status = "ONLINE"
		existing.LastSeen = time.Now()
	} else {
		node.Status = "ONLINE"
		node.LastSeen = time.Now()
		e.nodes[node.ID] = node
	}
}

// RemoveNode marks a node as offline.
func (e *Engine) RemoveNode(id string) {
	e.mu.Lock()
	defer e.mu.Unlock()

	if n, ok := e.nodes[id]; ok {
		n.Status = "OFFLINE"
	}
}

// GetNodes returns a slice of current nodes.
func (e *Engine) GetNodes() []*Node {
	e.mu.RLock()
	defer e.mu.RUnlock()

	res := make([]*Node, 0, len(e.nodes))
	for _, n := range e.nodes {
		nodeCopy := *n
		res = append(res, &nodeCopy)
	}
	return res
}

// GetSpeed returns current total speed up/down (bytes/s).
func (e *Engine) GetSpeed() (float64, float64) {
	e.mu.RLock()
	defer e.mu.RUnlock()
	return e.speedUp, e.speedDown
}

// selectNode picks a target node using Round-Robin.
func (e *Engine) selectNode() (*Node, error) {
	e.mu.RLock()
	defer e.mu.RUnlock()

	var onlineNodes []*Node
	for _, n := range e.nodes {
		if n.Status == "ONLINE" && n.Port > 0 {
			onlineNodes = append(onlineNodes, n)
		}
	}

	if len(onlineNodes) == 0 {
		return nil, fmt.Errorf("no available online nodes")
	}

	idx := atomic.AddUint64(&e.rrIndex, 1) - 1
	return onlineNodes[idx%uint64(len(onlineNodes))], nil
}

// Server Side: Accept incoming tunnel connections
func (e *Engine) acceptServer(l net.Listener) {
	for {
		conn, err := l.Accept()
		if err != nil {
			return
		}
		go e.handleServerConn(conn)
	}
}

func (e *Engine) handleServerConn(conn net.Conn) {
	defer conn.Close()

	reader := bufio.NewReader(conn)
	line, err := reader.ReadBytes('\n')
	if err != nil {
		return
	}

	var hdr Header
	if err := json.Unmarshal(line, &hdr); err != nil {
		return
	}

	targetConn, err := net.DialTimeout("tcp", hdr.Host, 10*time.Second)
	if err != nil {
		return
	}
	defer targetConn.Close()

	selfID := fmt.Sprintf("%s@%s:%d", e.cfg.Hostname, e.cfg.Advertise, e.cfg.ServerPort)
	e.mu.Lock()
	if me, ok := e.nodes[selfID]; ok {
		atomic.AddInt64(&me.ActiveConn, 1)
		defer atomic.AddInt64(&me.ActiveConn, -1)
	}
	e.mu.Unlock()

	multiReader := io.MultiReader(reader, conn)
	e.relayReader(conn, multiReader, targetConn)
}

func (e *Engine) relayReader(conn net.Conn, connReader io.Reader, targetConn net.Conn) {
	var wg sync.WaitGroup
	wg.Add(2)
	closeBoth := func() {
		_ = conn.Close()
		_ = targetConn.Close()
	}

	// conn (client tunnel) -> targetConn
	go func() {
		defer wg.Done()
		defer closeBoth()
		io.Copy(targetConn, connReader)
	}()

	// targetConn -> conn
	go func() {
		defer wg.Done()
		defer closeBoth()
		io.Copy(conn, targetConn)
	}()

	wg.Wait()
}

// Client Side: Accept SOCKS5 proxy connections
func (e *Engine) acceptClient(l net.Listener) {
	for {
		conn, err := l.Accept()
		if err != nil {
			return
		}
		go e.handleSocks5Conn(conn)
	}
}

func (e *Engine) handleSocks5Conn(conn net.Conn) {
	defer conn.Close()

	// 1. SOCKS5 Handshake
	buf := make([]byte, 256)
	if _, err := io.ReadFull(conn, buf[:2]); err != nil {
		return
	}
	if buf[0] != 0x05 { // VER
		return
	}
	nmethods := int(buf[1])
	if _, err := io.ReadFull(conn, buf[:nmethods]); err != nil {
		return
	}
	// NO AUTHENTICATION REQUIRED
	if _, err := conn.Write([]byte{0x05, 0x00}); err != nil {
		return
	}

	// 2. SOCKS5 Request
	if _, err := io.ReadFull(conn, buf[:4]); err != nil {
		return
	}
	cmd := buf[1]
	addrType := buf[3]

	if cmd != 0x01 { // CONNECT
		conn.Write([]byte{0x05, 0x07, 0x00, 0x01, 0, 0, 0, 0, 0, 0}) // Command not supported
		return
	}

	var host string
	switch addrType {
	case 0x01: // IPv4
		if _, err := io.ReadFull(conn, buf[:4]); err != nil {
			return
		}
		host = net.IP(buf[:4]).String()
	case 0x03: // Domain name
		if _, err := io.ReadFull(conn, buf[:1]); err != nil {
			return
		}
		domainLen := int(buf[0])
		if _, err := io.ReadFull(conn, buf[:domainLen]); err != nil {
			return
		}
		host = string(buf[:domainLen])
	case 0x04: // IPv6
		if _, err := io.ReadFull(conn, buf[:16]); err != nil {
			return
		}
		host = net.IP(buf[:16]).String()
	default:
		return
	}

	if _, err := io.ReadFull(conn, buf[:2]); err != nil {
		return
	}
	port := int(buf[0])<<8 | int(buf[1])
	targetHost := net.JoinHostPort(host, strconv.Itoa(port))

	// Select node to proxy with automatic failover retry
	var serverConn net.Conn
	var node *Node

	for retries := 0; retries < 3; retries++ {
		selected, err := e.selectNode()
		if err != nil {
			break
		}

		nodeAddr := net.JoinHostPort(selected.IP, strconv.Itoa(selected.Port))
		if selected.IsMe || selected.IP == "127.0.0.1" || selected.IP == "" {
			nodeAddr = fmt.Sprintf("127.0.0.1:%d", selected.Port)
		}

		dialConn, err := net.DialTimeout("tcp", nodeAddr, 2*time.Second)
		if err != nil && selected.IP != "127.0.0.1" {
			dialConn, err = net.DialTimeout("tcp", fmt.Sprintf("127.0.0.1:%d", selected.Port), 2*time.Second)
		}
		if err != nil {
			e.RemoveNode(selected.ID)
			continue
		}
		serverConn = dialConn
		node = selected
		break
	}

	if serverConn == nil || node == nil {
		conn.Write([]byte{0x05, 0x04, 0x00, 0x01, 0, 0, 0, 0, 0, 0})
		return
	}
	defer serverConn.Close()

	// Send Header
	hdr := Header{
		Version:    1,
		Host:       targetHost,
		ClientPort: e.cfg.ClientPort,
		ClientHost: e.cfg.Hostname,
	}
	hdrBytes, _ := json.Marshal(hdr)
	hdrBytes = append(hdrBytes, '\n')

	if _, err := serverConn.Write(hdrBytes); err != nil {
		conn.Write([]byte{0x05, 0x01, 0x00, 0x01, 0, 0, 0, 0, 0, 0})
		return
	}

	// Send SOCKS5 Success Response
	if _, err := conn.Write([]byte{0x05, 0x00, 0x00, 0x01, 0, 0, 0, 0, 0, 0}); err != nil {
		return
	}

	// Update node stats
	atomic.AddInt64(&node.ActiveConn, 1)
	defer atomic.AddInt64(&node.ActiveConn, -1)

	// Relay traffic and record bytes
	e.relayWithStats(conn, serverConn, node)
}

func (e *Engine) relay(c1, c2 net.Conn) {
	var wg sync.WaitGroup
	wg.Add(2)
	closeBoth := func() {
		_ = c1.Close()
		_ = c2.Close()
	}
	go func() {
		defer wg.Done()
		defer closeBoth()
		io.Copy(c1, c2)
	}()
	go func() {
		defer wg.Done()
		defer closeBoth()
		io.Copy(c2, c1)
	}()
	wg.Wait()
}

func (e *Engine) relayWithStats(clientConn, serverConn net.Conn, node *Node) {
	var wg sync.WaitGroup
	wg.Add(2)
	closeBoth := func() {
		_ = clientConn.Close()
		_ = serverConn.Close()
	}

	// client -> server (upload)
	go func() {
		defer wg.Done()
		defer closeBoth()
		buf := make([]byte, 32*1024)
		for {
			n, err := clientConn.Read(buf)
			if n > 0 {
				atomic.AddUint64(&e.bytesUp, uint64(n))
				atomic.AddUint64(&node.BytesUp, uint64(n))
				if _, werr := serverConn.Write(buf[:n]); werr != nil {
					break
				}
			}
			if err != nil {
				break
			}
		}
	}()

	// server -> client (download)
	go func() {
		defer wg.Done()
		defer closeBoth()
		buf := make([]byte, 32*1024)
		for {
			n, err := serverConn.Read(buf)
			if n > 0 {
				atomic.AddUint64(&e.bytesDown, uint64(n))
				atomic.AddUint64(&node.BytesDown, uint64(n))
				if _, werr := clientConn.Write(buf[:n]); werr != nil {
					break
				}
			}
			if err != nil {
				break
			}
		}
	}()

	wg.Wait()
}

func (e *Engine) speedLoop(ctx context.Context) {
	ticker := time.NewTicker(1 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			e.mu.Lock()
			now := time.Now()
			dt := now.Sub(e.lastCalc).Seconds()
			if dt > 0 {
				curUp := atomic.LoadUint64(&e.bytesUp)
				curDown := atomic.LoadUint64(&e.bytesDown)

				e.speedUp = float64(curUp-e.lastUp) / dt
				e.speedDown = float64(curDown-e.lastDown) / dt

				e.lastUp = curUp
				e.lastDown = curDown
				e.lastCalc = now
			}
			e.mu.Unlock()
		}
	}
}
