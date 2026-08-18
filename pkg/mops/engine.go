package mops

import (
	"bufio"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

// Node status constants
const (
	NodeStatusOnline     = "ONLINE"
	NodeStatusNoInternet = "NO_INTERNET"
	NodeStatusOffline    = "OFFLINE"
)

// Header defines the tunnel handshake protocol header.
type Header struct {
	Version    int    `json:"version"`
	Proto      string `json:"proto,omitempty"` // "proxy" or "file"
	Host       string `json:"host,omitempty"`
	FileName   string `json:"file_name,omitempty"`
	FileSize   int64  `json:"file_size,omitempty"`
	FileHash   string `json:"file_hash,omitempty"`
	ClientPort int    `json:"client_port,omitempty"`
	ClientHost string `json:"client_host,omitempty"`
}

// Trailer defines the end-of-stream verification payload.
type Trailer struct {
	FileHash string `json:"file_hash,omitempty"`
}

// Node represents a cluster proxy server node.
type Node struct {
	ID           string    `json:"id"`
	Hostname     string    `json:"hostname"`
	IP           string    `json:"ip"`
	Port         int       `json:"port"`
	APIPort      int       `json:"api_port"`
	Role         string    `json:"role"`
	Status       string    `json:"status"`
	ActiveConn   int64     `json:"active_conns"`
	SuccessConns uint64    `json:"success_conns"`
	FailConns    uint64    `json:"fail_conns"`
	BytesUp      uint64    `json:"bytes_up"`
	BytesDown    uint64    `json:"bytes_down"`
	SpeedUp      float64   `json:"speed_up"`
	SpeedDown    float64   `json:"speed_down"`
	LastSeen     time.Time `json:"last_seen"`
	IsMe         bool      `json:"is_me"`
}

// TransferProgress represents real-time file transfer progress metadata.
type TransferProgress struct {
	FileName         string  `json:"file_name"`
	TransferredBytes int64   `json:"transferred_bytes"`
	TotalBytes       int64   `json:"total_bytes"`
	Percentage       float64 `json:"percentage"`
	Status           string  `json:"status"` // "IDLE", "TRANSFERRING", "COMPLETED", "FAILED"
	Direction        string  `json:"direction"` // "SEND" or "RECEIVE"
}

// Config defines the configuration for MOPS Engine.
type Config struct {
	ServerPort  int
	ClientPort  int
	APIPort     int
	ListenAddr  string
	Hostname    string
	Advertise   string
	Strategy    string // "random" or "hash"
	DownloadDir string
}

// Engine coordinates the proxy server, client, and node pool.
type Engine struct {
	cfg Config
	mu  sync.RWMutex

	nodes map[string]*Node

	serverListener net.Listener
	clientListener net.Listener
	apiServer      *APIServer
	discovery      *Discovery

	running       bool
	serverRunning bool
	clientRunning bool
	cancel        context.CancelFunc

	rrIndex uint64 // Round-Robin counter

	// Client Outbound Traffic stats
	bytesUp   uint64
	bytesDown uint64

	// Client Outbound Speed calculation
	speedUp   float64
	speedDown float64
	lastUp    uint64
	lastDown  uint64
	lastCalc  time.Time

	// Server Provider Traffic stats (as a proxy provider)
	serverBytesUp   uint64
	serverBytesDown uint64

	// Server Provider Speed calculation
	serverSpeedUp   float64
	serverSpeedDown float64
	lastServerUp    uint64
	lastServerDown  uint64

	// Active file transfer progress
	progress TransferProgress

	// Internet access probe
	probeFunc     func() bool
	probeInterval time.Duration
}

// NewEngine creates a new proxy Engine instance.
func NewEngine(cfg Config) *Engine {
	explicitDownloadDir := cfg.DownloadDir
	explicitStrategy := cfg.Strategy
	explicitListenAddr := cfg.ListenAddr
	explicitHostname := cfg.Hostname
	explicitAdvertise := cfg.Advertise
	explicitServerPort := cfg.ServerPort
	explicitClientPort := cfg.ClientPort
	explicitAPIPort := cfg.APIPort

	cfg = LoadPersistentConfig(cfg)

	if explicitDownloadDir != "" {
		cfg.DownloadDir = explicitDownloadDir
	}
	if explicitStrategy != "" {
		cfg.Strategy = explicitStrategy
	}
	if explicitListenAddr != "" {
		cfg.ListenAddr = explicitListenAddr
	}
	if explicitHostname != "" {
		cfg.Hostname = explicitHostname
	}
	if explicitAdvertise != "" {
		cfg.Advertise = explicitAdvertise
	}
	if explicitServerPort > 0 {
		cfg.ServerPort = explicitServerPort
	}
	if explicitClientPort > 0 {
		cfg.ClientPort = explicitClientPort
	}
	if explicitAPIPort > 0 {
		cfg.APIPort = explicitAPIPort
	}

	if cfg.ListenAddr == "" {
		cfg.ListenAddr = "127.0.0.1"
	}
	if cfg.Strategy == "" {
		cfg.Strategy = "random"
	}
	if cfg.DownloadDir == "" {
		cfg.DownloadDir = GetDefaultDownloadDir()
	}

	return &Engine{
		cfg:           cfg,
		nodes:         make(map[string]*Node),
		lastCalc:      time.Now(),
		probeInterval: 15 * time.Second,
		progress: TransferProgress{
			Status: "IDLE",
		},
	}
}

// GetDefaultDownloadDir returns the user's system Downloads folder (e.g. C:\Users\<Username>\Downloads),
// falling back to "./downloads" if user home dir cannot be determined.
func GetDefaultDownloadDir() string {
	home, err := os.UserHomeDir()
	if err == nil && home != "" {
		return filepath.Join(home, "Downloads")
	}
	return "./downloads"
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

	// Add self node (initial state ONLINE, will be verified by probeLoop)
	selfIP := ResolveAdvertiseIP(e.cfg.Advertise)
	selfID := fmt.Sprintf("%s@%s:%d", e.cfg.Hostname, selfIP, e.cfg.ServerPort)
	selfNode := &Node{
		ID:       selfID,
		Hostname: e.cfg.Hostname,
		IP:       selfIP,
		Port:     e.cfg.ServerPort,
		APIPort:  e.cfg.APIPort,
		Role:     "Both",
		Status:   NodeStatusOnline,
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
		e.serverRunning = true
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
		e.clientRunning = true
		go e.acceptClient(l)
	}

	// Start RESTful API Server
	if e.cfg.APIPort > 0 {
		apiSrv := NewAPIServer(e)
		if err := apiSrv.Start(e.cfg.APIPort, e.cfg.ListenAddr); err != nil {
			if e.serverListener != nil {
				e.serverListener.Close()
			}
			if e.clientListener != nil {
				e.clientListener.Close()
			}
			return fmt.Errorf("failed to start API listener on port %d: %w", e.cfg.APIPort, err)
		}
		e.apiServer = apiSrv
	}

	// Speed calculation loop
	go e.speedLoop(ctx)

	// Internet access probe loop
	go e.probeLoop(ctx)

	// Node health check and cluster metrics sync loop
	go e.nodeHealthLoop(ctx)

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
	e.serverRunning = false
	e.clientRunning = false

	if e.cancel != nil {
		e.cancel()
	}

	if e.apiServer != nil {
		e.apiServer.Stop()
	}

	if e.serverListener != nil {
		e.serverListener.Close()
	}
	if e.clientListener != nil {
		e.clientListener.Close()
	}
}

// GetClientEnabled returns whether client proxy is currently running.
func (e *Engine) GetClientEnabled() bool {
	e.mu.RLock()
	defer e.mu.RUnlock()
	return e.clientRunning
}

// GetServerEnabled returns whether server proxy is currently running.
func (e *Engine) GetServerEnabled() bool {
	e.mu.RLock()
	defer e.mu.RUnlock()
	return e.serverRunning
}

// SetClientEnabled dynamically starts or stops the client SOCKS5 listener.
func (e *Engine) SetClientEnabled(enable bool) error {
	e.mu.Lock()
	if !e.running {
		e.mu.Unlock()
		return fmt.Errorf("engine is not running")
	}

	if enable {
		if e.clientRunning {
			e.mu.Unlock()
			return nil
		}
		if e.cfg.ClientPort <= 0 {
			e.mu.Unlock()
			return fmt.Errorf("client port is disabled or invalid (%d)", e.cfg.ClientPort)
		}
		cliAddr := fmt.Sprintf("%s:%d", e.cfg.ListenAddr, e.cfg.ClientPort)
		l, err := net.Listen("tcp", cliAddr)
		if err != nil {
			e.mu.Unlock()
			return fmt.Errorf("failed to start client listener on %s: %w", cliAddr, err)
		}
		e.clientListener = l
		e.clientRunning = true
		e.mu.Unlock()

		go e.acceptClient(l)
		return nil
	} else {
		if !e.clientRunning {
			e.mu.Unlock()
			return nil
		}
		if e.clientListener != nil {
			_ = e.clientListener.Close()
			e.clientListener = nil
		}
		e.clientRunning = false
		e.mu.Unlock()
		return nil
	}
}

// SetServerEnabled dynamically starts or stops the server TCP listener.
func (e *Engine) SetServerEnabled(enable bool) error {
	e.mu.Lock()
	if !e.running {
		e.mu.Unlock()
		return fmt.Errorf("engine is not running")
	}

	if enable {
		if e.serverRunning {
			e.mu.Unlock()
			return nil
		}
		if e.cfg.ServerPort <= 0 {
			e.mu.Unlock()
			return fmt.Errorf("server port is disabled or invalid (%d)", e.cfg.ServerPort)
		}
		srvAddr := fmt.Sprintf("0.0.0.0:%d", e.cfg.ServerPort)
		l, err := net.Listen("tcp", srvAddr)
		if err != nil {
			e.mu.Unlock()
			return fmt.Errorf("failed to start server listener on %s: %w", srvAddr, err)
		}
		e.serverListener = l
		e.serverRunning = true
		e.mu.Unlock()

		go e.acceptServer(l)
		return nil
	} else {
		if !e.serverRunning {
			e.mu.Unlock()
			return nil
		}
		if e.serverListener != nil {
			_ = e.serverListener.Close()
			e.serverListener = nil
		}
		e.serverRunning = false
		e.mu.Unlock()
		return nil
	}
}

// UpdateNode adds or updates a remote node in the pool.
func (e *Engine) UpdateNode(node *Node) {
	e.mu.Lock()
	defer e.mu.Unlock()

	status := node.Status
	if status == "" {
		status = NodeStatusOnline
	}

	if existing, ok := e.nodes[node.ID]; ok {
		existing.Hostname = node.Hostname
		existing.IP = node.IP
		existing.Port = node.Port
		if node.APIPort > 0 {
			existing.APIPort = node.APIPort
		}
		if node.Role != "" {
			existing.Role = node.Role
		}
		existing.Status = status
		existing.LastSeen = time.Now()
	} else {
		node.Status = status
		node.LastSeen = time.Now()
		e.nodes[node.ID] = node
	}
}

// RemoveNode marks a node as offline.
func (e *Engine) RemoveNode(id string) {
	e.mu.Lock()
	defer e.mu.Unlock()

	if n, ok := e.nodes[id]; ok {
		n.Status = NodeStatusOffline
	}
}

// GetNodes returns a slice of current nodes.
func (e *Engine) GetNodes() []*Node {
	e.mu.RLock()
	defer e.mu.RUnlock()

	res := make([]*Node, 0, len(e.nodes))
	for _, n := range e.nodes {
		nodeCopy := *n
		if nodeCopy.IsMe {
			nodeCopy.BytesUp = atomic.LoadUint64(&e.serverBytesUp)
			nodeCopy.BytesDown = atomic.LoadUint64(&e.serverBytesDown)
			nodeCopy.SpeedUp = e.serverSpeedUp
			nodeCopy.SpeedDown = e.serverSpeedDown
		}
		res = append(res, &nodeCopy)
	}

	sort.Slice(res, func(i, j int) bool {
		if res[i].IsMe != res[j].IsMe {
			return res[i].IsMe
		}
		if res[i].IP != res[j].IP {
			return res[i].IP < res[j].IP
		}
		return res[i].Port < res[j].Port
	})

	return res
}

// GetAdvertiseIP returns the current advertise IP.
func (e *Engine) GetAdvertiseIP() string {
	e.mu.RLock()
	defer e.mu.RUnlock()
	return e.cfg.Advertise
}

// GetSpeed returns current client outbound proxy speed up/down (bytes/s).
func (e *Engine) GetSpeed() (float64, float64) {
	e.mu.RLock()
	defer e.mu.RUnlock()
	return e.speedUp, e.speedDown
}

// GetServerSpeed returns current server provider speed up/down (bytes/s) and total bytes up/down.
func (e *Engine) GetServerSpeed() (float64, float64, uint64, uint64) {
	e.mu.RLock()
	defer e.mu.RUnlock()
	return e.serverSpeedUp, e.serverSpeedDown, atomic.LoadUint64(&e.serverBytesUp), atomic.LoadUint64(&e.serverBytesDown)
}

// SetDownloadDir dynamically updates the file download save directory.
func (e *Engine) SetDownloadDir(dir string) error {
	if dir == "" {
		return fmt.Errorf("download directory cannot be empty")
	}
	if err := os.MkdirAll(dir, 0755); err != nil {
		return fmt.Errorf("failed to create download directory %s: %w", dir, err)
	}
	e.mu.Lock()
	e.cfg.DownloadDir = dir
	e.mu.Unlock()

	_ = UpdatePersistentConfig(func(p *PersistentConfig) {
		p.DownloadDir = dir
	})
	return nil
}

// GetDownloadDir returns the configured download directory.
func (e *Engine) GetDownloadDir() string {
	e.mu.RLock()
	defer e.mu.RUnlock()
	if e.cfg.DownloadDir == "" {
		return GetDefaultDownloadDir()
	}
	return e.cfg.DownloadDir
}

// GetTransferProgress returns the current file transfer progress.
func (e *Engine) GetTransferProgress() TransferProgress {
	e.mu.RLock()
	defer e.mu.RUnlock()
	return e.progress
}

func (e *Engine) updateTransferProgress(fileName string, transferred, total int64, status, direction string) {
	e.mu.Lock()
	defer e.mu.Unlock()
	var pct float64
	if total > 0 {
		pct = float64(transferred) / float64(total) * 100.0
		if pct > 100.0 {
			pct = 100.0
		}
	}
	e.progress = TransferProgress{
		FileName:         fileName,
		TransferredBytes: transferred,
		TotalBytes:       total,
		Percentage:       pct,
		Status:           status,
		Direction:        direction,
	}
}

// selectNode picks a target node using Round-Robin.
func (e *Engine) selectNode() (*Node, error) {
	e.mu.RLock()
	defer e.mu.RUnlock()

	var onlineNodes []*Node
	for _, n := range e.nodes {
		if n.Status == NodeStatusOnline && n.Port > 0 {
			onlineNodes = append(onlineNodes, n)
		}
	}

	if len(onlineNodes) == 0 {
		return nil, fmt.Errorf("no available online nodes")
	}

	// Deterministic sort by ID to ensure stable round-robin distribution
	sort.Slice(onlineNodes, func(i, j int) bool {
		return onlineNodes[i].ID < onlineNodes[j].ID
	})

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

	_ = conn.SetReadDeadline(time.Now().Add(10 * time.Second))

	reader := bufio.NewReader(conn)
	line, err := reader.ReadBytes('\n')
	if err != nil {
		return
	}

	var hdr Header
	if err := json.Unmarshal(line, &hdr); err != nil {
		return
	}

	selfIP := ResolveAdvertiseIP(e.cfg.Advertise)
	selfID := fmt.Sprintf("%s@%s:%d", e.cfg.Hostname, selfIP, e.cfg.ServerPort)
	e.mu.Lock()
	var meNode *Node
	if me, ok := e.nodes[selfID]; ok {
		meNode = me
		atomic.AddInt64(&me.ActiveConn, 1)
		defer atomic.AddInt64(&me.ActiveConn, -1)
	}
	e.mu.Unlock()

	multiReader := io.MultiReader(reader, conn)

	if hdr.Proto == "file" {
		_ = conn.SetReadDeadline(time.Time{})
		e.handleIncomingFile(multiReader, hdr, meNode)
		return
	}

	targetConn, err := net.DialTimeout("tcp", hdr.Host, 10*time.Second)
	if err != nil {
		if meNode != nil {
			atomic.AddUint64(&meNode.FailConns, 1)
		}
		fmt.Printf("[MOPS ERROR] Server failed to dial outbound target [%s]: %v\n", hdr.Host, err)
		_, _ = conn.Write([]byte{0x01})
		return
	}
	defer targetConn.Close()

	if meNode != nil {
		atomic.AddUint64(&meNode.SuccessConns, 1)
	}

	if _, err := conn.Write([]byte{0x00}); err != nil {
		return
	}

	_ = conn.SetReadDeadline(time.Time{})

	e.relayServerWithStats(conn, multiReader, targetConn, meNode)
}

func (e *Engine) handleIncomingFile(reader io.Reader, hdr Header, meNode *Node) {
	e.mu.RLock()
	saveDir := e.cfg.DownloadDir
	e.mu.RUnlock()
	if saveDir == "" {
		saveDir = GetDefaultDownloadDir()
	}

	outFile, filePath, err := createUniqueFile(saveDir, hdr.FileName)
	if err != nil {
		e.updateTransferProgress(hdr.FileName, 0, hdr.FileSize, "FAILED", "RECEIVE")
		return
	}

	e.updateTransferProgress(hdr.FileName, 0, hdr.FileSize, "TRANSFERRING", "RECEIVE")

	limitReader := io.LimitReader(reader, hdr.FileSize)
	hasher := sha256.New()
	buf := make([]byte, 1024*1024) // 1MB Buffer
	var transferred int64

	for {
		n, err := limitReader.Read(buf)
		if n > 0 {
			transferred += int64(n)
			atomic.AddUint64(&e.serverBytesDown, uint64(n))
			if meNode != nil {
				atomic.AddUint64(&meNode.BytesDown, uint64(n))
			}
			_, _ = outFile.Write(buf[:n])
			_, _ = hasher.Write(buf[:n])
			e.updateTransferProgress(hdr.FileName, transferred, hdr.FileSize, "TRANSFERRING", "RECEIVE")
		}
		if err != nil {
			break
		}
	}

	_ = outFile.Sync()
	_ = outFile.Close()

	// Read Trailer JSON line from remaining stream
	bufReader := bufio.NewReader(reader)
	trailerLine, err := bufReader.ReadBytes('\n')
	if err == nil && len(trailerLine) > 0 {
		var tr Trailer
		if err := json.Unmarshal(trailerLine, &tr); err == nil && tr.FileHash != "" {
			calcHash := fmt.Sprintf("sha256:%s", hex.EncodeToString(hasher.Sum(nil)))
			if calcHash != tr.FileHash {
				_ = os.Remove(filePath)
				e.updateTransferProgress(hdr.FileName, transferred, hdr.FileSize, "FAILED", "RECEIVE")
				return
			}
		}
	}
	e.updateTransferProgress(hdr.FileName, hdr.FileSize, hdr.FileSize, "COMPLETED", "RECEIVE")
}

func createUniqueFile(dir, fileName string) (*os.File, string, error) {
	if dir == "" {
		dir = GetDefaultDownloadDir()
	}
	if err := os.MkdirAll(dir, 0755); err != nil {
		return nil, "", err
	}

	fileName = strings.ReplaceAll(fileName, "\\", "/")
	baseName := filepath.Base(fileName)
	if baseName == "." || baseName == "/" || baseName == "" {
		baseName = "file.bin"
	}
	ext := filepath.Ext(baseName)
	nameWithoutExt := strings.TrimSuffix(baseName, ext)

	target := filepath.Join(dir, baseName)
	f, err := os.OpenFile(target, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0666)
	if err == nil {
		return f, target, nil
	}
	if !errors.Is(err, os.ErrExist) && !os.IsExist(err) {
		return nil, "", err
	}

	for i := 1; ; i++ {
		newName := fmt.Sprintf("%s(%d)%s", nameWithoutExt, i, ext)
		target = filepath.Join(dir, newName)
		f, err := os.OpenFile(target, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0666)
		if err == nil {
			return f, target, nil
		}
		if !errors.Is(err, os.ErrExist) && !os.IsExist(err) {
			return nil, "", err
		}
	}
}

// SendFileToNode connects to a target node and streams file data using "file" protocol.
func (e *Engine) SendFileToNode(targetIP string, targetPort int, fileName string, reader io.Reader, fileSize int64, fileHash string) (string, error) {
	e.updateTransferProgress(fileName, 0, fileSize, "TRANSFERRING", "SEND")
	addr := fmt.Sprintf("%s:%d", targetIP, targetPort)
	conn, err := net.DialTimeout("tcp", addr, 10*time.Second)
	if err != nil {
		e.updateTransferProgress(fileName, 0, fileSize, "FAILED", "SEND")
		return "", fmt.Errorf("failed to connect to node %s: %w", addr, err)
	}
	defer conn.Close()

	hdr := Header{
		Version:    1,
		Proto:      "file",
		FileName:   fileName,
		FileSize:   fileSize,
		ClientHost: e.cfg.Advertise,
		ClientPort: e.cfg.ClientPort,
	}

	data, err := json.Marshal(hdr)
	if err != nil {
		e.updateTransferProgress(fileName, 0, fileSize, "FAILED", "SEND")
		return "", err
	}
	data = append(data, '\n')
	if _, err := conn.Write(data); err != nil {
		e.updateTransferProgress(fileName, 0, fileSize, "FAILED", "SEND")
		return "", err
	}

	hasher := sha256.New()
	buf := make([]byte, 1024*1024) // 1MB Buffer
	var transferred int64

	for {
		n, rerr := reader.Read(buf)
		if n > 0 {
			transferred += int64(n)
			atomic.AddUint64(&e.bytesUp, uint64(n))
			_, _ = hasher.Write(buf[:n])
			if _, werr := conn.Write(buf[:n]); werr != nil {
				e.updateTransferProgress(fileName, transferred, fileSize, "FAILED", "SEND")
				return "", werr
			}
			e.updateTransferProgress(fileName, transferred, fileSize, "TRANSFERRING", "SEND")
		}
		if rerr != nil {
			if rerr == io.EOF {
				break
			}
			e.updateTransferProgress(fileName, transferred, fileSize, "FAILED", "SEND")
			return "", rerr
		}
	}

	// Send Trailer JSON
	if fileHash == "" {
		fileHash = fmt.Sprintf("sha256:%s", hex.EncodeToString(hasher.Sum(nil)))
	}

	tr := Trailer{
		FileHash: fileHash,
	}
	trData, err := json.Marshal(tr)
	if err != nil {
		e.updateTransferProgress(fileName, transferred, fileSize, "FAILED", "SEND")
		return "", err
	}
	trData = append(trData, '\n')
	_, err = conn.Write(trData)
	if err != nil {
		e.updateTransferProgress(fileName, transferred, fileSize, "FAILED", "SEND")
		return "", err
	}

	e.updateTransferProgress(fileName, fileSize, fileSize, "COMPLETED", "SEND")
	return fileHash, nil
}

func (e *Engine) relayServerWithStats(conn net.Conn, connReader io.Reader, targetConn net.Conn, meNode *Node) {
	var wg sync.WaitGroup
	wg.Add(2)
	closeBoth := func() {
		_ = conn.Close()
		_ = targetConn.Close()
	}

	// conn (client tunnel) -> targetConn (Upload)
	go func() {
		defer wg.Done()
		defer closeBoth()
		buf := make([]byte, 32*1024)
		for {
			n, err := connReader.Read(buf)
			if n > 0 {
				atomic.AddUint64(&e.serverBytesUp, uint64(n))
				if meNode != nil {
					atomic.AddUint64(&meNode.BytesUp, uint64(n))
				}
				if _, werr := targetConn.Write(buf[:n]); werr != nil {
					break
				}
			}
			if err != nil {
				break
			}
		}
	}()

	// targetConn -> conn (Download)
	go func() {
		defer wg.Done()
		defer closeBoth()
		buf := make([]byte, 32*1024)
		for {
			n, err := targetConn.Read(buf)
			if n > 0 {
				atomic.AddUint64(&e.serverBytesDown, uint64(n))
				if meNode != nil {
					atomic.AddUint64(&meNode.BytesDown, uint64(n))
				}
				if _, werr := conn.Write(buf[:n]); werr != nil {
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
				// Client Outbound Speed
				curUp := atomic.LoadUint64(&e.bytesUp)
				curDown := atomic.LoadUint64(&e.bytesDown)
				e.speedUp = float64(curUp-e.lastUp) / dt
				e.speedDown = float64(curDown-e.lastDown) / dt
				e.lastUp = curUp
				e.lastDown = curDown

				// Server Provider Speed
				curSrvUp := atomic.LoadUint64(&e.serverBytesUp)
				curSrvDown := atomic.LoadUint64(&e.serverBytesDown)
				e.serverSpeedUp = float64(curSrvUp-e.lastServerUp) / dt
				e.serverSpeedDown = float64(curSrvDown-e.lastServerDown) / dt
				e.lastServerUp = curSrvUp
				e.lastServerDown = curSrvDown

				e.lastCalc = now
			}
			e.mu.Unlock()
		}
	}
}

func (e *Engine) dialAndHandshakeNode(targetHost string) (*Node, net.Conn, error) {
	var lastErr error

	for retries := 0; retries < 3; retries++ {
		selected, err := e.selectNode()
		if err != nil {
			lastErr = err
			break
		}

		nodeAddr := net.JoinHostPort(selected.IP, strconv.Itoa(selected.Port))
		if selected.IsMe || selected.IP == "127.0.0.1" || selected.IP == "" {
			nodeAddr = fmt.Sprintf("127.0.0.1:%d", selected.Port)
		}

		dialConn, err := net.DialTimeout("tcp", nodeAddr, 2*time.Second)
		if err != nil && selected.IP != "127.0.0.1" && selected.IsMe {
			dialConn, err = net.DialTimeout("tcp", fmt.Sprintf("127.0.0.1:%d", selected.Port), 2*time.Second)
		}
		if err != nil {
			atomic.AddUint64(&selected.FailConns, 1)
			e.RemoveNode(selected.ID)
			fmt.Printf("[MOPS WARN] Failed to connect node [%s] (%s): %v, marking OFFLINE and retrying next...\n", selected.Hostname, nodeAddr, err)
			lastErr = err
			continue
		}

		// Send MOPS tunnel Header
		hdr := Header{
			Version:    1,
			Host:       targetHost,
			ClientPort: e.cfg.ClientPort,
			ClientHost: e.cfg.Hostname,
		}
		hdrBytes, _ := json.Marshal(hdr)
		hdrBytes = append(hdrBytes, '\n')

		_ = dialConn.SetDeadline(time.Now().Add(5 * time.Second))
		if _, err := dialConn.Write(hdrBytes); err != nil {
			atomic.AddUint64(&selected.FailConns, 1)
			_ = dialConn.Close()
			fmt.Printf("[MOPS WARN] Failed to send tunnel header to node [%s]: %v, retrying next...\n", selected.Hostname, err)
			lastErr = err
			continue
		}

		// Read Server Handshake ACK
		ack := make([]byte, 1)
		if _, err := io.ReadFull(dialConn, ack); err != nil || ack[0] != 0x00 {
			atomic.AddUint64(&selected.FailConns, 1)
			_ = dialConn.Close()
			if err != nil {
				fmt.Printf("[MOPS WARN] Node [%s] closed handshake unexpectedly for [%s]: %v, retrying next...\n", selected.Hostname, targetHost, err)
				lastErr = err
			} else {
				fmt.Printf("[MOPS WARN] Node [%s] failed to reach outbound target [%s], retrying next...\n", selected.Hostname, targetHost)
				lastErr = fmt.Errorf("node %s failed to connect target %s (ack=%d)", selected.Hostname, targetHost, ack[0])
			}
			continue
		}

		_ = dialConn.SetDeadline(time.Time{})
		return selected, dialConn, nil
	}

	if lastErr == nil {
		lastErr = fmt.Errorf("no available online nodes")
	}
	return nil, nil, lastErr
}

// Client Side: Accept SOCKS5 & HTTP hybrid proxy connections
func (e *Engine) acceptClient(l net.Listener) {
	for {
		conn, err := l.Accept()
		if err != nil {
			return
		}
		go e.handleClientConn(conn)
	}
}

func (e *Engine) handleClientConn(conn net.Conn) {
	_ = conn.SetReadDeadline(time.Now().Add(10 * time.Second))

	reader := bufio.NewReader(conn)
	peek, err := reader.Peek(1)
	if err != nil {
		_ = conn.Close()
		return
	}

	if peek[0] == 0x05 {
		e.handleSocks5Conn(conn, reader)
	} else {
		e.handleHttpProxyConn(conn, reader)
	}
}

func (e *Engine) handleSocks5Conn(conn net.Conn, reader *bufio.Reader) {
	defer conn.Close()

	// 1. SOCKS5 Handshake
	buf := make([]byte, 256)
	if _, err := io.ReadFull(reader, buf[:2]); err != nil {
		return
	}
	if buf[0] != 0x05 { // VER
		return
	}
	nmethods := int(buf[1])
	if _, err := io.ReadFull(reader, buf[:nmethods]); err != nil {
		return
	}
	// NO AUTHENTICATION REQUIRED
	if _, err := conn.Write([]byte{0x05, 0x00}); err != nil {
		return
	}

	// 2. SOCKS5 Request
	if _, err := io.ReadFull(reader, buf[:4]); err != nil {
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
		if _, err := io.ReadFull(reader, buf[:4]); err != nil {
			return
		}
		host = net.IP(buf[:4]).String()
	case 0x03: // Domain name
		if _, err := io.ReadFull(reader, buf[:1]); err != nil {
			return
		}
		domainLen := int(buf[0])
		if _, err := io.ReadFull(reader, buf[:domainLen]); err != nil {
			return
		}
		host = string(buf[:domainLen])
	case 0x04: // IPv6
		if _, err := io.ReadFull(reader, buf[:16]); err != nil {
			return
		}
		host = net.IP(buf[:16]).String()
	default:
		return
	}

	if _, err := io.ReadFull(reader, buf[:2]); err != nil {
		return
	}
	port := int(buf[0])<<8 | int(buf[1])
	targetHost := net.JoinHostPort(host, strconv.Itoa(port))

	node, serverConn, err := e.dialAndHandshakeNode(targetHost)
	if err != nil {
		fmt.Printf("[MOPS ERROR] All available nodes failed for target [%s]: %v\n", targetHost, err)
		conn.Write([]byte{0x05, 0x04, 0x00, 0x01, 0, 0, 0, 0, 0, 0})
		return
	}
	defer serverConn.Close()

	fmt.Printf("[MOPS PROXY SOCKS5] Selected Node [%s] (%s:%d) for target [%s]\n", node.Hostname, node.IP, node.Port, targetHost)

	// Send SOCKS5 Success Response
	if _, err := conn.Write([]byte{0x05, 0x00, 0x00, 0x01, 0, 0, 0, 0, 0, 0}); err != nil {
		return
	}

	_ = conn.SetReadDeadline(time.Time{})

	// Relay traffic and record bytes
	e.relayWithStats(conn, serverConn, node)
}

func (e *Engine) handleHttpProxyConn(conn net.Conn, reader *bufio.Reader) {
	defer conn.Close()

	// Read first line (Request Line)
	reqLine, err := reader.ReadString('\n')
	if err != nil {
		return
	}

	parts := strings.Fields(reqLine)
	if len(parts) < 2 {
		return
	}

	method := strings.ToUpper(parts[0])
	rawURL := parts[1]

	var targetHost string
	var initialPayload []byte

	if method == "CONNECT" {
		// HTTPS Tunnel: CONNECT host:port HTTP/1.1
		targetHost = rawURL
		if !strings.Contains(targetHost, ":") {
			targetHost = targetHost + ":443"
		}

		// Read & discard remaining HTTP headers up to empty line
		for {
			line, err := reader.ReadString('\n')
			if err != nil || line == "\r\n" || line == "\n" {
				break
			}
		}
	} else {
		// Plain HTTP: GET http://host:port/path HTTP/1.1
		if strings.HasPrefix(rawURL, "http://") {
			trimmed := strings.TrimPrefix(rawURL, "http://")
			slashIdx := strings.Index(trimmed, "/")
			if slashIdx != -1 {
				targetHost = trimmed[:slashIdx]
				parts[1] = trimmed[slashIdx:]
			} else {
				targetHost = trimmed
				parts[1] = "/"
			}
		} else {
			targetHost = rawURL
		}

		if !strings.Contains(targetHost, ":") {
			targetHost = targetHost + ":80"
		}

		var headerBuf bytes.Buffer
		headerBuf.WriteString(strings.Join(parts, " ") + "\r\n")

		for {
			line, err := reader.ReadString('\n')
			if err != nil {
				break
			}
			if strings.HasPrefix(strings.ToLower(line), "proxy-connection:") {
				line = "Connection:" + strings.TrimPrefix(line, "Proxy-Connection:")
			}
			headerBuf.WriteString(line)
			if line == "\r\n" || line == "\n" {
				break
			}
		}
		initialPayload = headerBuf.Bytes()
	}

	node, serverConn, err := e.dialAndHandshakeNode(targetHost)
	if err != nil {
		fmt.Printf("[MOPS ERROR] All available nodes failed for target [%s]: %v\n", targetHost, err)
		if method == "CONNECT" {
			_, _ = conn.Write([]byte("HTTP/1.1 502 Bad Gateway\r\n\r\n"))
		} else {
			_, _ = conn.Write([]byte("HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/plain\r\n\r\nMOPS: Remote nodes failed to reach target host\r\n"))
		}
		return
	}
	if method == "CONNECT" {
		// Reply 200 Connection Established to client
		if _, err := conn.Write([]byte("HTTP/1.1 200 Connection Established\r\n\r\n")); err != nil {
			return
		}
	} else {
		// Write reconstructed initial HTTP request to server
		if len(initialPayload) > 0 {
			if _, err := serverConn.Write(initialPayload); err != nil {
				return
			}
		}
	}

	_ = conn.SetReadDeadline(time.Time{})

	// Relay traffic
	clientMultiReader := io.MultiReader(reader, conn)
	e.relayHttpWithStats(conn, clientMultiReader, serverConn, node)
}

func (e *Engine) relayHttpWithStats(clientConn net.Conn, clientReader io.Reader, serverConn net.Conn, node *Node) {
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
			n, err := clientReader.Read(buf)
			if n > 0 {
				atomic.AddUint64(&e.bytesUp, uint64(n))
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




// GetAdvertise returns the current configured advertise IP.
func (e *Engine) GetAdvertise() string {
	e.mu.RLock()
	defer e.mu.RUnlock()
	return e.cfg.Advertise
}

// SetAdvertise updates the broadcast advertise IP and saves persistent config.
func (e *Engine) SetAdvertise(ip string) error {
	e.mu.Lock()
	e.cfg.Advertise = ip
	e.mu.Unlock()

	return UpdatePersistentConfig(func(p *PersistentConfig) {
		p.Advertise = ip
	})
}

// SetDiscovery links discovery service to engine for advertise control.
func (e *Engine) SetDiscovery(d *Discovery) {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.discovery = d
}

// SetProbeFunc overrides default internet access probe function for testing.
func (e *Engine) SetProbeFunc(fn func() bool) {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.probeFunc = fn
}

// SetProbeInterval sets the probe check interval (default 15s).
func (e *Engine) SetProbeInterval(d time.Duration) {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.probeInterval = d
}

// DefaultInternetProbe checks external network connectivity via lightweight DNS port dials and HTTP 204.
// Priority: 223.5.5.5:53 (AliDNS, 2s timeout), fallback: 1.1.1.1:53 (Cloudflare DNS, 2s timeout), HTTP 204.
func DefaultInternetProbe() bool {
	conn, err := net.DialTimeout("tcp", "223.5.5.5:53", 2*time.Second)
	if err == nil {
		_ = conn.Close()
		return true
	}
	conn2, err := net.DialTimeout("tcp", "1.1.1.1:53", 2*time.Second)
	if err == nil {
		_ = conn2.Close()
		return true
	}
	client := &http.Client{Timeout: 2 * time.Second}
	resp, err := client.Get("http://connect.rom.miui.com/generate_204")
	if err == nil {
		_ = resp.Body.Close()
		return true
	}
	return false
}

func (e *Engine) checkInternet() bool {
	e.mu.RLock()
	fn := e.probeFunc
	e.mu.RUnlock()

	if fn != nil {
		return fn()
	}
	return DefaultInternetProbe()
}

// TriggerProbe runs an immediate internet probe check.
func (e *Engine) TriggerProbe() {
	e.probeOnce()
}

func (e *Engine) probeOnce() {
	hasInternet := e.checkInternet()

	e.mu.Lock()
	selfIP := ResolveAdvertiseIP(e.cfg.Advertise)
	selfID := fmt.Sprintf("%s@%s:%d", e.cfg.Hostname, selfIP, e.cfg.ServerPort)
	me, hasMe := e.nodes[selfID]
	disc := e.discovery

	if hasInternet {
		if hasMe {
			me.Status = NodeStatusOnline
			me.LastSeen = time.Now()
		}
		e.mu.Unlock()
		if disc != nil {
			disc.ResumeAdvertise()
		}
	} else {
		if hasMe {
			me.Status = NodeStatusNoInternet
			me.LastSeen = time.Now()
		}
		e.mu.Unlock()
		if disc != nil {
			disc.PauseAdvertise()
		}
	}
}

func (e *Engine) probeLoop(ctx context.Context) {
	// Initial probe check
	e.probeOnce()

	e.mu.RLock()
	interval := e.probeInterval
	e.mu.RUnlock()
	if interval <= 0 {
		interval = 15 * time.Second
	}

	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			e.probeOnce()
		}
	}
}

func (e *Engine) nodeHealthLoop(ctx context.Context) {
	ticker := time.NewTicker(1 * time.Second)
	defer ticker.Stop()

	client := &http.Client{
		Timeout: 900 * time.Millisecond,
	}

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			e.checkAndSyncNodes(client)
		}
	}
}

type probeTarget struct {
	ID      string
	IP      string
	Port    int
	APIPort int
}

func (e *Engine) checkAndSyncNodes(client *http.Client) {
	var targets []probeTarget

	e.mu.RLock()
	for _, n := range e.nodes {
		if !n.IsMe {
			targets = append(targets, probeTarget{
				ID:      n.ID,
				IP:      n.IP,
				Port:    n.Port,
				APIPort: n.APIPort,
			})
		}
	}
	e.mu.RUnlock()

	if len(targets) == 0 {
		return
	}

	var wg sync.WaitGroup
	for _, target := range targets {
		wg.Add(1)
		go func(tgt probeTarget) {
			defer wg.Done()
			e.probeAndSyncSingleNode(client, tgt)
		}(target)
	}
	wg.Wait()
}

func (e *Engine) probeAndSyncSingleNode(client *http.Client, target probeTarget) {
	// 1. Try REST API nodes sync if APIPort is known (> 0)
	if target.APIPort > 0 {
		apiHostPort := net.JoinHostPort(target.IP, strconv.Itoa(target.APIPort))
		url := fmt.Sprintf("http://%s/api/v1/nodes", apiHostPort)
		resp, err := client.Get(url)
		if err == nil && resp.StatusCode == http.StatusOK {
			var apiResp struct {
				Code int     `json:"code"`
				Data []*Node `json:"data"`
			}
			if decErr := json.NewDecoder(resp.Body).Decode(&apiResp); decErr == nil && apiResp.Code == 200 {
				e.mu.Lock()
				if n, ok := e.nodes[target.ID]; ok {
					n.Status = NodeStatusOnline
					for _, remoteNode := range apiResp.Data {
						if remoteNode.IsMe {
							n.BytesUp = remoteNode.BytesUp
							n.BytesDown = remoteNode.BytesDown
							n.SpeedUp = remoteNode.SpeedUp
							n.SpeedDown = remoteNode.SpeedDown
							n.ActiveConn = remoteNode.ActiveConn
							n.SuccessConns = remoteNode.SuccessConns
							n.FailConns = remoteNode.FailConns
							break
						}
					}
					n.LastSeen = time.Now()
				}
				e.mu.Unlock()
				_ = resp.Body.Close()
				return
			}
			_ = resp.Body.Close()
		} else if resp != nil {
			_ = resp.Body.Close()
		}
	}

	// 2. Fallback: TCP Server Port Dial Probe
	tcpAddr := net.JoinHostPort(target.IP, strconv.Itoa(target.Port))
	conn, err := net.DialTimeout("tcp", tcpAddr, 1200*time.Millisecond)
	if err == nil {
		_ = conn.Close()
		e.mu.Lock()
		if n, ok := e.nodes[target.ID]; ok {
			n.Status = NodeStatusOnline
			n.LastSeen = time.Now()
		}
		e.mu.Unlock()
	} else {
		// Unreachable
		e.mu.Lock()
		if n, ok := e.nodes[target.ID]; ok {
			n.Status = NodeStatusOffline
		}
		e.mu.Unlock()
	}
}


