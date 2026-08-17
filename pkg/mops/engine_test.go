package mops

import (
	"bufio"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"net"
	"os"
	"path/filepath"
	"sync/atomic"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

var testPortCounter int32 = 10800

func getFreePort() int {
	for i := 0; i < 100; i++ {
		p := atomic.AddInt32(&testPortCounter, 1)
		if p > 10899 {
			atomic.StoreInt32(&testPortCounter, 10800)
			p = 10800
		}
		l, err := net.Listen("tcp", fmt.Sprintf("127.0.0.1:%d", p))
		if err == nil {
			l.Close()
			return int(p)
		}
	}
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return 0
	}
	defer l.Close()
	return l.Addr().(*net.TCPAddr).Port
}

func TestEngineSocks5ProxyFlow(t *testing.T) {
	// 1. Setup a dummy target TCP server
	freeP := getFreePort()
	targetListener, err := net.Listen("tcp", fmt.Sprintf("127.0.0.1:%d", freeP))
	if err != nil {
		targetListener, err = net.Listen("tcp", "127.0.0.1:0")
	}
	require.NoError(t, err)
	require.NoError(t, err)
	defer targetListener.Close()

	targetPort := targetListener.Addr().(*net.TCPAddr).Port

	go func() {
		conn, err := targetListener.Accept()
		if err != nil {
			return
		}
		defer conn.Close()

		buf := make([]byte, 1024)
		n, _ := conn.Read(buf)
		if n > 0 {
			conn.Write([]byte("ECHO: " + string(buf[:n])))
		}
	}()

	// 2. Start Engine with dynamic free ports
	serverPort := getFreePort()
	clientPort := getFreePort()
	cfg := Config{
		ServerPort: serverPort,
		ClientPort: clientPort,
		ListenAddr: "127.0.0.1",
		Hostname:   "TestNode",
		Advertise:  "127.0.0.1",
	}
	engine := NewEngine(cfg)
	ctx := context.Background()
	require.NoError(t, engine.Start(ctx))
	defer engine.Stop()

	// Wait for listener ready
	time.Sleep(50 * time.Millisecond)

	// 3. Connect via Client SOCKS5 Proxy
	proxyAddr := fmt.Sprintf("127.0.0.1:%d", clientPort)
	conn, err := net.Dial("tcp", proxyAddr)
	require.NoError(t, err)
	defer conn.Close()

	// SOCKS5 Handshake: [VER, NMETHODS, METHODS]
	_, err = conn.Write([]byte{0x05, 0x01, 0x00})
	require.NoError(t, err)

	resp := make([]byte, 2)
	_, err = io.ReadFull(conn, resp)
	require.NoError(t, err)
	assert.Equal(t, byte(0x05), resp[0])
	assert.Equal(t, byte(0x00), resp[1])

	// SOCKS5 Request: [VER, CMD, RSV, ATYP, DST.ADDR (IPv4), DST.PORT]
	req := []byte{0x05, 0x01, 0x00, 0x01, 127, 0, 0, 1, byte(targetPort >> 8), byte(targetPort & 0xff)}
	_, err = conn.Write(req)
	require.NoError(t, err)

	socksResp := make([]byte, 10)
	_, err = io.ReadFull(conn, socksResp)
	require.NoError(t, err)
	assert.Equal(t, byte(0x05), socksResp[0])
	assert.Equal(t, byte(0x00), socksResp[1]) // Success

	// Data Transfer
	msg := "Hello MOPS Go Engine"
	_, err = conn.Write([]byte(msg))
	require.NoError(t, err)

	readBuf := make([]byte, 1024)
	n, err := conn.Read(readBuf)
	require.NoError(t, err)
	assert.Equal(t, "ECHO: "+msg, string(readBuf[:n]))
	conn.Close()
}

func TestEngineSocks5DomainAndErrorCases(t *testing.T) {
	// 1. Target Server
	targetListener, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	defer targetListener.Close()

	targetPort := targetListener.Addr().(*net.TCPAddr).Port

	go func() {
		conn, err := targetListener.Accept()
		if err != nil {
			return
		}
		defer conn.Close()
		buf := make([]byte, 256)
		n, _ := conn.Read(buf)
		if n > 0 {
			conn.Write([]byte("DOMAIN_OK: " + string(buf[:n])))
		}
	}()

	// 2. Engine
	cfg := Config{
		ServerPort: getFreePort(),
		ClientPort: getFreePort(),
		ListenAddr: "127.0.0.1",
		Hostname:   "DomainNode",
		Advertise:  "127.0.0.1",
	}
	engine := NewEngine(cfg)
	ctx := context.Background()
	require.NoError(t, engine.Start(ctx))
	defer engine.Stop()

	// Update existing node test
	engine.UpdateNode(&Node{
		ID:       fmt.Sprintf("%s-%d", cfg.Hostname, cfg.ServerPort),
		Hostname: "DomainNode-Updated",
		IP:       "127.0.0.1",
		Port:     cfg.ServerPort,
	})

	// Dial Proxy
	proxyAddr := fmt.Sprintf("127.0.0.1:%d", cfg.ClientPort)

	// Test 1: SOCKS5 Domain Address Type (0x03)
	conn, err := net.Dial("tcp", proxyAddr)
	require.NoError(t, err)

	_, _ = conn.Write([]byte{0x05, 0x01, 0x00})
	resp := make([]byte, 2)
	_, _ = io.ReadFull(conn, resp)

	domain := "localhost"
	req := []byte{0x05, 0x01, 0x00, 0x03, byte(len(domain))}
	req = append(req, []byte(domain)...)
	req = append(req, byte(targetPort>>8), byte(targetPort&0xff))

	_, _ = conn.Write(req)
	socksResp := make([]byte, 10)
	_, _ = io.ReadFull(conn, socksResp)
	assert.Equal(t, byte(0x00), socksResp[1])

	_, _ = conn.Write([]byte("DomainData"))
	readBuf := make([]byte, 256)
	n, _ := conn.Read(readBuf)
	assert.Equal(t, "DOMAIN_OK: DomainData", string(readBuf[:n]))
	conn.Close()

	// Test 2: Invalid SOCKS Version (0x04)
	connErr, err := net.Dial("tcp", proxyAddr)
	require.NoError(t, err)
	_, _ = connErr.Write([]byte{0x04, 0x01, 0x00}) // Invalid VER
	connErr.Close()

	// Test 3: Unsupported CMD (0x02 BIND)
	connCmd, err := net.Dial("tcp", proxyAddr)
	require.NoError(t, err)
	_, _ = connCmd.Write([]byte{0x05, 0x01, 0x00})
	_, _ = io.ReadFull(connCmd, resp)
	reqUnsupportedCmd := []byte{0x05, 0x02, 0x00, 0x01, 127, 0, 0, 1, 0, 80}
	_, _ = connCmd.Write(reqUnsupportedCmd)
	socksRespErr := make([]byte, 10)
	_, _ = io.ReadFull(connCmd, socksRespErr)
	assert.Equal(t, byte(0x07), socksRespErr[1]) // Command not supported
	connCmd.Close()
}

func TestTunnelHeaderProtocolErrors(t *testing.T) {
	// Server Node
	serverPort := getFreePort()
	cfg := Config{
		ServerPort: serverPort,
		ClientPort: 0,
		ListenAddr: "127.0.0.1",
		Hostname:   "HeaderTestNode",
		Advertise:  "127.0.0.1",
	}
	engine := NewEngine(cfg)
	ctx := context.Background()
	require.NoError(t, engine.Start(ctx))
	defer engine.Stop()

	// 1. Send invalid JSON Header to Server Port
	conn, err := net.Dial("tcp", fmt.Sprintf("127.0.0.1:%d", serverPort))
	require.NoError(t, err)
	_, _ = conn.Write([]byte("INVALID_JSON_HEADER\n"))

	// Expect server to close connection
	buf := make([]byte, 100)
	n, _ := conn.Read(buf)
	assert.Equal(t, 0, n)
	conn.Close()
}

func TestEnginePortConflictAndDuplicates(t *testing.T) {
	port := getFreePort()
	// Create a listener on 0.0.0.0 to occupy the port
	l, err := net.Listen("tcp", fmt.Sprintf("0.0.0.0:%d", port))
	require.NoError(t, err)
	defer l.Close()

	cfg := Config{
		ServerPort: port,
		ClientPort: getFreePort(),
		ListenAddr: "127.0.0.1",
		Hostname:   "ConflictHost",
	}
	engine := NewEngine(cfg)
	ctx := context.Background()

	// 1. Should fail to start due to port in use
	err = engine.Start(ctx)
	assert.Error(t, err)

	// 2. Duplicate Start when already running
	cfg2 := Config{
		ServerPort: getFreePort(),
		ClientPort: getFreePort(),
		ListenAddr: "127.0.0.1",
		Hostname:   "DupHost",
	}
	engine2 := NewEngine(cfg2)
	require.NoError(t, engine2.Start(ctx))
	defer engine2.Stop()

	errDup := engine2.Start(ctx)
	assert.Error(t, errDup)
	assert.Contains(t, errDup.Error(), "already running")
}

func TestEngineSocks5IPv6Support(t *testing.T) {
	targetListener, err := net.Listen("tcp", ":0")
	require.NoError(t, err)
	defer targetListener.Close()

	targetPort := targetListener.Addr().(*net.TCPAddr).Port

	go func() {
		conn, err := targetListener.Accept()
		if err != nil {
			return
		}
		defer conn.Close()
		buf := make([]byte, 256)
		n, _ := conn.Read(buf)
		if n > 0 {
			conn.Write([]byte("IPV6_OK: " + string(buf[:n])))
		}
	}()

	clientPort := getFreePort()
	serverPort := getFreePort()
	cfg := Config{
		ServerPort: serverPort,
		ClientPort: clientPort,
		ListenAddr: "127.0.0.1",
		Hostname:   "IPv6Node",
		Advertise:  "127.0.0.1",
	}
	engine := NewEngine(cfg)
	ctx := context.Background()
	require.NoError(t, engine.Start(ctx))
	defer engine.Stop()

	proxyConn, err := net.Dial("tcp", fmt.Sprintf("127.0.0.1:%d", clientPort))
	require.NoError(t, err)
	defer proxyConn.Close()

	// SOCKS5 Auth
	proxyConn.Write([]byte{0x05, 0x01, 0x00})
	resp := make([]byte, 2)
	io.ReadFull(proxyConn, resp)

	// SOCKS5 IPv6 Request (0x04)
	ip6 := net.ParseIP("::1").To16()
	req := []byte{0x05, 0x01, 0x00, 0x04}
	req = append(req, ip6...)
	req = append(req, byte(targetPort>>8), byte(targetPort&0xff))

	proxyConn.Write(req)
	socksResp := make([]byte, 10)
	io.ReadFull(proxyConn, socksResp)
	assert.Equal(t, byte(0x00), socksResp[1])

	proxyConn.Write([]byte("IPv6Data"))
	readBuf := make([]byte, 256)
	n, _ := proxyConn.Read(readBuf)
	assert.Equal(t, "IPV6_OK: IPv6Data", string(readBuf[:n]))
}

func TestEngineAllNodesOffline(t *testing.T) {
	clientPort := getFreePort()
	cfg := Config{
		ServerPort: 0,
		ClientPort: clientPort,
		ListenAddr: "127.0.0.1",
		Hostname:   "OfflineTestClient",
	}
	engine := NewEngine(cfg)
	ctx := context.Background()
	require.NoError(t, engine.Start(ctx))
	defer engine.Stop()

	// Add an offline node
	engine.UpdateNode(&Node{
		ID:       "dead-node",
		Hostname: "DeadPC",
		IP:       "127.0.0.1",
		Port:     9999,
		Status:   "OFFLINE",
	})

	proxyConn, err := net.Dial("tcp", fmt.Sprintf("127.0.0.1:%d", clientPort))
	require.NoError(t, err)
	defer proxyConn.Close()

	proxyConn.Write([]byte{0x05, 0x01, 0x00})
	resp := make([]byte, 2)
	io.ReadFull(proxyConn, resp)

	// Request CONNECT
	req := []byte{0x05, 0x01, 0x00, 0x01, 127, 0, 0, 1, 0, 80}
	proxyConn.Write(req)
	socksResp := make([]byte, 10)
	io.ReadFull(proxyConn, socksResp)

	// Expect 0x04 (Host unreachable)
	assert.Equal(t, byte(0x04), socksResp[1])
}

func TestFileTransferProtocol(t *testing.T) {
	tempDir, err := os.MkdirTemp("", "mops_test_download_*")
	require.NoError(t, err)
	defer os.RemoveAll(tempDir)

	serverPort := getFreePort()
	cfg := Config{
		ServerPort:  serverPort,
		ClientPort:  0,
		ListenAddr:  "127.0.0.1",
		Hostname:    "FileReceiver",
		DownloadDir: tempDir,
	}

	engine := NewEngine(cfg)
	ctx := context.Background()
	require.NoError(t, engine.Start(ctx))
	defer engine.Stop()

	fileContent := []byte("Hello MOPS File Transfer Test!")
	hasher := sha256.New()
	hasher.Write(fileContent)
	fileHash := fmt.Sprintf("sha256:%s", hex.EncodeToString(hasher.Sum(nil)))

	// Send file to receiver node
	_, err = engine.SendFileToNode("127.0.0.1", serverPort, "test_doc.txt", bytes.NewReader(fileContent), int64(len(fileContent)), fileHash)
	require.NoError(t, err)

	// Verify file received in tempDir
	targetPath := filepath.Join(tempDir, "test_doc.txt")
	require.Eventually(t, func() bool {
		info, err := os.Stat(targetPath)
		return err == nil && info.Size() == int64(len(fileContent))
	}, 2*time.Second, 20*time.Millisecond)

	data, err := os.ReadFile(targetPath)
	require.NoError(t, err)
	assert.Equal(t, fileContent, data)
}

func TestFileTransferAutoRename(t *testing.T) {
	tempDir, err := os.MkdirTemp("", "mops_test_rename_*")
	require.NoError(t, err)
	defer os.RemoveAll(tempDir)

	serverPort := getFreePort()
	cfg := Config{
		ServerPort:  serverPort,
		ClientPort:  0,
		ListenAddr:  "127.0.0.1",
		Hostname:    "RenameReceiver",
		DownloadDir: tempDir,
	}

	engine := NewEngine(cfg)
	ctx := context.Background()
	require.NoError(t, engine.Start(ctx))
	defer engine.Stop()

	fileContent := []byte("Content Version 1")
	_, err = engine.SendFileToNode("127.0.0.1", serverPort, "sample.txt", bytes.NewReader(fileContent), int64(len(fileContent)), "")
	require.NoError(t, err)

	// Send second file with same name
	fileContent2 := []byte("Content Version 2")
	_, err = engine.SendFileToNode("127.0.0.1", serverPort, "sample.txt", bytes.NewReader(fileContent2), int64(len(fileContent2)), "")
	require.NoError(t, err)

	path1 := filepath.Join(tempDir, "sample.txt")
	path2 := filepath.Join(tempDir, "sample(1).txt")

	require.Eventually(t, func() bool {
		info1, err1 := os.Stat(path1)
		info2, err2 := os.Stat(path2)
		return err1 == nil && info1.Size() == int64(len(fileContent)) && err2 == nil && info2.Size() == int64(len(fileContent2))
	}, 2*time.Second, 20*time.Millisecond)

	data1, _ := os.ReadFile(path1)
	data2, _ := os.ReadFile(path2)

	assert.Equal(t, fileContent, data1)
	assert.Equal(t, fileContent2, data2)
}

func TestFileTransferZeroBytes(t *testing.T) {
	tempDir, err := os.MkdirTemp("", "mops_test_zero_*")
	require.NoError(t, err)
	defer os.RemoveAll(tempDir)

	serverPort := getFreePort()
	cfg := Config{
		ServerPort:  serverPort,
		ClientPort:  0,
		ListenAddr:  "127.0.0.1",
		Hostname:    "ZeroBytesReceiver",
		DownloadDir: tempDir,
	}

	engine := NewEngine(cfg)
	ctx := context.Background()
	require.NoError(t, engine.Start(ctx))
	defer engine.Stop()

	// Send 0 bytes file
	_, err = engine.SendFileToNode("127.0.0.1", serverPort, "empty.txt", bytes.NewReader([]byte{}), 0, "")
	require.NoError(t, err)

	targetPath := filepath.Join(tempDir, "empty.txt")
	require.Eventually(t, func() bool {
		_, err := os.Stat(targetPath)
		return err == nil
	}, 2*time.Second, 20*time.Millisecond)

	stat, err := os.Stat(targetPath)
	require.NoError(t, err)
	assert.Equal(t, int64(0), stat.Size())
}

func TestFileTransferTrailerHashCorrupted(t *testing.T) {
	tempDir, err := os.MkdirTemp("", "mops_test_corrupt_*")
	require.NoError(t, err)
	defer os.RemoveAll(tempDir)

	serverPort := getFreePort()
	cfg := Config{
		ServerPort:  serverPort,
		ClientPort:  0,
		ListenAddr:  "127.0.0.1",
		Hostname:    "CorruptReceiver",
		DownloadDir: tempDir,
	}

	engine := NewEngine(cfg)
	ctx := context.Background()
	require.NoError(t, engine.Start(ctx))
	defer engine.Stop()

	// Send file with intentionally mismatched/corrupted Hash
	fileContent := []byte("Valid content but hash will mismatch")
	wrongHash := "sha256:0000000000000000000000000000000000000000000000000000000000000000"

	_, err = engine.SendFileToNode("127.0.0.1", serverPort, "corrupted.txt", bytes.NewReader(fileContent), int64(len(fileContent)), wrongHash)
	require.NoError(t, err)

	// Verify file was removed due to corrupt Hash mismatch
	time.Sleep(250 * time.Millisecond)
	targetPath := filepath.Join(tempDir, "corrupted.txt")
	assert.NoFileExists(t, targetPath)
}

func TestEngineTrafficAndSpeedStats(t *testing.T) {
	targetListener, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	defer targetListener.Close()

	targetPort := targetListener.Addr().(*net.TCPAddr).Port

	go func() {
		conn, err := targetListener.Accept()
		if err != nil {
			return
		}
		defer conn.Close()

		buf := make([]byte, 32*1024)
		for {
			n, err := conn.Read(buf)
			if n > 0 {
				conn.Write(buf[:n])
			}
			if err != nil {
				break
			}
		}
	}()

	serverPort := getFreePort()
	clientPort := getFreePort()
	apiPort := getFreePort()
	cfg := Config{
		ServerPort: serverPort,
		ClientPort: clientPort,
		APIPort:    apiPort,
		ListenAddr: "127.0.0.1",
		Hostname:   "StatsNode",
		Advertise:  "127.0.0.1",
	}
	engine := NewEngine(cfg)
	ctx := context.Background()
	require.NoError(t, engine.Start(ctx))
	defer engine.Stop()

	// Dial SOCKS5 proxy
	proxyConn, err := net.Dial("tcp", fmt.Sprintf("127.0.0.1:%d", clientPort))
	require.NoError(t, err)
	defer proxyConn.Close()

	proxyConn.Write([]byte{0x05, 0x01, 0x00})
	resp := make([]byte, 2)
	_, err = io.ReadFull(proxyConn, resp)
	require.NoError(t, err)

	req := []byte{0x05, 0x01, 0x00, 0x01, 127, 0, 0, 1, byte(targetPort >> 8), byte(targetPort & 0xff)}
	proxyConn.Write(req)
	socksResp := make([]byte, 10)
	_, err = io.ReadFull(proxyConn, socksResp)
	require.NoError(t, err)
	assert.Equal(t, byte(0x00), socksResp[1])

	// Send large payload to trigger traffic stats
	payload := make([]byte, 64*1024)
	for i := range payload {
		payload[i] = byte(i % 256)
	}
	_, err = proxyConn.Write(payload)
	require.NoError(t, err)

	recvBuf := make([]byte, len(payload))
	_, err = io.ReadFull(proxyConn, recvBuf)
	require.NoError(t, err)
	assert.Equal(t, payload, recvBuf)

	// Wait for speed calculation loop (1s ticker)
	time.Sleep(1100 * time.Millisecond)

	speedUp, speedDown := engine.GetSpeed()
	assert.Greater(t, atomic.LoadUint64(&engine.bytesUp), uint64(0))
	assert.Greater(t, atomic.LoadUint64(&engine.bytesDown), uint64(0))
	assert.True(t, speedUp > 0 || speedDown > 0, "Expected non-zero speed calculation")

	// Verify via REST API as well
	statusData, nodes, err := fetchStatusFromAPI(apiPort)
	require.NoError(t, err)
	assert.Greater(t, statusData.BytesUp, uint64(0))
	assert.Greater(t, statusData.BytesDown, uint64(0))
	assert.Len(t, nodes, 1)
	assert.Greater(t, nodes[0].BytesUp, uint64(0))
	assert.Greater(t, nodes[0].BytesDown, uint64(0))
}

func TestEngineSetClientAndServerEnabled(t *testing.T) {
	// 1. Test before engine start
	engineUnstarted := NewEngine(Config{ClientPort: 10860, ServerPort: 10861})
	assert.ErrorContains(t, engineUnstarted.SetClientEnabled(true), "engine is not running")
	assert.ErrorContains(t, engineUnstarted.SetServerEnabled(true), "engine is not running")

	// 2. Start engine
	clientPort := getFreePort()
	serverPort := getFreePort()
	cfg := Config{
		ClientPort: clientPort,
		ServerPort: serverPort,
		APIPort:    getFreePort(),
	}
	engine := NewEngine(cfg)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	require.NoError(t, engine.Start(ctx))
	defer engine.Stop()

	assert.True(t, engine.GetClientEnabled())
	assert.True(t, engine.GetServerEnabled())

	// 3. Test idempotent disable & enable
	require.NoError(t, engine.SetClientEnabled(false))
	assert.False(t, engine.GetClientEnabled())
	require.NoError(t, engine.SetClientEnabled(false)) // repeat disable

	require.NoError(t, engine.SetClientEnabled(true))
	assert.True(t, engine.GetClientEnabled())
	require.NoError(t, engine.SetClientEnabled(true)) // repeat enable

	require.NoError(t, engine.SetServerEnabled(false))
	assert.False(t, engine.GetServerEnabled())
	require.NoError(t, engine.SetServerEnabled(false)) // repeat disable

	require.NoError(t, engine.SetServerEnabled(true))
	assert.True(t, engine.GetServerEnabled())
	require.NoError(t, engine.SetServerEnabled(true)) // repeat enable
}

func TestEngineDownloadDirAndProgress(t *testing.T) {
	eng := NewEngine(Config{
		DownloadDir: "./test_downloads",
	})
	assert.Equal(t, "./test_downloads", eng.GetDownloadDir())

	newDir := filepath.Join(os.TempDir(), "mops_custom_downloads")
	defer os.RemoveAll(newDir)

	err := eng.SetDownloadDir(newDir)
	require.NoError(t, err)
	assert.Equal(t, newDir, eng.GetDownloadDir())

	err = eng.SetDownloadDir("")
	assert.Error(t, err)

	prog := eng.GetTransferProgress()
	assert.Equal(t, "IDLE", prog.Status)
}

func TestDefaultInternetProbe(t *testing.T) {
	// DefaultInternetProbe tries to dial 223.5.5.5:53 / 1.1.1.1:53 with 2s timeout.
	// We verify it returns a boolean without panic or hang.
	result := DefaultInternetProbe()
	t.Logf("DefaultInternetProbe result: %v", result)
}

func TestNodeThreeStatesAndSelectNode(t *testing.T) {
	eng := NewEngine(Config{
		ServerPort: 10870,
		ClientPort: 10871,
		Hostname:   "SelectNodeTester",
		Advertise:  "127.0.0.1",
	})
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Initial start with self node
	require.NoError(t, eng.Start(ctx))
	defer eng.Stop()

	// Add remote nodes with 3 distinct states
	eng.UpdateNode(&Node{
		ID:       "node-online",
		Hostname: "NodeOnline",
		IP:       "192.168.1.101",
		Port:     10080,
		Status:   NodeStatusOnline,
	})
	eng.UpdateNode(&Node{
		ID:       "node-no-internet",
		Hostname: "NodeNoInternet",
		IP:       "192.168.1.102",
		Port:     10080,
		Status:   NodeStatusNoInternet,
	})
	eng.UpdateNode(&Node{
		ID:       "node-offline",
		Hostname: "NodeOffline",
		IP:       "192.168.1.103",
		Port:     10080,
		Status:   NodeStatusOffline,
	})

	// Manually set self node to NO_INTERNET to test selection strictly filters only ONLINE nodes
	selfIP := ResolveAdvertiseIP("127.0.0.1")
	selfID := fmt.Sprintf("SelectNodeTester@%s:10870", selfIP)
	eng.mu.Lock()
	if me, ok := eng.nodes[selfID]; ok {
		me.Status = NodeStatusNoInternet
	}
	eng.mu.Unlock()

	// Only node-online should be picked
	for i := 0; i < 5; i++ {
		selected, err := eng.selectNode()
		require.NoError(t, err)
		assert.Equal(t, "node-online", selected.ID)
		assert.Equal(t, NodeStatusOnline, selected.Status)
	}

	// Now mark node-online as OFFLINE
	eng.RemoveNode("node-online")

	// Now all nodes are either NO_INTERNET or OFFLINE, selectNode should return error
	_, err := eng.selectNode()
	assert.ErrorContains(t, err, "no available online nodes")
}

func TestProbeLoopStateTransition(t *testing.T) {
	eng := NewEngine(Config{
		ServerPort: 10880,
		ClientPort: 10881,
		Hostname:   "ProbeTransitionHost",
		Advertise:  "127.0.0.1",
	})
	eng.SetProbeInterval(50 * time.Millisecond)

	var internetStatus int32 = 1 // 1: online, 0: offline
	eng.SetProbeFunc(func() bool {
		return atomic.LoadInt32(&internetStatus) == 1
	})

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	require.NoError(t, eng.Start(ctx))
	defer eng.Stop()

	disc := NewDiscovery(eng)
	require.NoError(t, disc.Start(ctx))
	defer disc.Stop()

	selfIP := ResolveAdvertiseIP("127.0.0.1")
	selfID := fmt.Sprintf("ProbeTransitionHost@%s:10880", selfIP)

	// 1. Initially online
	eng.TriggerProbe()
	eng.mu.RLock()
	assert.Equal(t, NodeStatusOnline, eng.nodes[selfID].Status)
	eng.mu.RUnlock()
	assert.False(t, disc.IsPaused())

	// 2. Simulate disconnect / no internet
	atomic.StoreInt32(&internetStatus, 0)
	eng.TriggerProbe()

	eng.mu.RLock()
	assert.Equal(t, NodeStatusNoInternet, eng.nodes[selfID].Status)
	eng.mu.RUnlock()
	assert.True(t, disc.IsPaused())

	// 3. Simulate internet restore
	atomic.StoreInt32(&internetStatus, 1)
	eng.TriggerProbe()

	eng.mu.RLock()
	assert.Equal(t, NodeStatusOnline, eng.nodes[selfID].Status)
	eng.mu.RUnlock()
	assert.False(t, disc.IsPaused())
}

func TestNodeConnectionCountersSuccessAndFail(t *testing.T) {
	// 1. Target Echo Server
	targetListener, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	defer targetListener.Close()
	targetPort := targetListener.Addr().(*net.TCPAddr).Port

	go func() {
		for {
			conn, err := targetListener.Accept()
			if err != nil {
				return
			}
			go func(c net.Conn) {
				defer c.Close()
				buf := make([]byte, 1024)
				n, _ := c.Read(buf)
				if n > 0 {
					c.Write([]byte("ECHO: " + string(buf[:n])))
				}
			}(conn)
		}
	}()

	// 2. Start Engine
	sPort := getFreePort()
	cPort := getFreePort()
	eng := NewEngine(Config{
		ServerPort: sPort,
		ClientPort: cPort,
		ListenAddr: "127.0.0.1",
		Hostname:   "CounterHost",
		Advertise:  "127.0.0.1",
	})
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	require.NoError(t, eng.Start(ctx))
	defer eng.Stop()

	// 3. Perform a successful SOCKS5 request
	proxyAddr := fmt.Sprintf("127.0.0.1:%d", cPort)
	conn, err := net.Dial("tcp", proxyAddr)
	require.NoError(t, err)
	_, _ = conn.Write([]byte{0x05, 0x01, 0x00})
	resp := make([]byte, 2)
	_, _ = io.ReadFull(conn, resp)
	req := []byte{0x05, 0x01, 0x00, 0x01, 127, 0, 0, 1, byte(targetPort >> 8), byte(targetPort & 0xff)}
	_, _ = conn.Write(req)
	sResp := make([]byte, 10)
	_, _ = io.ReadFull(conn, sResp)
	_, _ = conn.Write([]byte("ping"))
	conn.Close()

	// Verify SuccessConns incremented
	nodes := eng.GetNodes()
	require.NotEmpty(t, nodes)
	var totalSuccess uint64
	for _, n := range nodes {
		totalSuccess += n.SuccessConns
	}
	assert.Greater(t, totalSuccess, uint64(0))

	// 4. Add a dummy unreachable node to test FailConns
	eng.UpdateNode(&Node{
		ID:       "dummy-fail-node",
		Hostname: "DummyFailNode",
		IP:       "192.0.2.1", // non-routable IP
		Port:     59999,
		Status:   NodeStatusOnline,
	})

	// Dial through proxy multiple times to trigger failover on dummy node
	for i := 0; i < 5; i++ {
		failConn, err := net.Dial("tcp", proxyAddr)
		if err == nil {
			_, _ = failConn.Write([]byte{0x05, 0x01, 0x00})
			_, _ = io.ReadFull(failConn, resp)
			_, _ = failConn.Write(req)
			failResp := make([]byte, 10)
			_, _ = io.ReadFull(failConn, failResp)
			failConn.Close()
		}
	}

	nodesAfter := eng.GetNodes()
	for _, n := range nodesAfter {
		if n.ID == "dummy-fail-node" {
			assert.Greater(t, n.FailConns, uint64(0))
			assert.Equal(t, NodeStatusOffline, n.Status)
		}
	}
}

func TestEngineHttpConnectProxyFlow(t *testing.T) {
	// 1. Target TCP Echo Server
	targetListener, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	defer targetListener.Close()
	targetPort := targetListener.Addr().(*net.TCPAddr).Port

	go func() {
		conn, err := targetListener.Accept()
		if err != nil {
			return
		}
		defer conn.Close()
		buf := make([]byte, 1024)
		n, _ := conn.Read(buf)
		if n > 0 {
			conn.Write([]byte("HTTP_ECHO: " + string(buf[:n])))
		}
	}()

	// 2. Start Engine
	sPort := getFreePort()
	cPort := getFreePort()
	eng := NewEngine(Config{
		ServerPort: sPort,
		ClientPort: cPort,
		ListenAddr: "127.0.0.1",
		Hostname:   "HttpProxyTester",
		Advertise:  "127.0.0.1",
	})
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	require.NoError(t, eng.Start(ctx))
	defer eng.Stop()

	// 3. Connect via HTTP CONNECT to hybrid 10081 port
	proxyConn, err := net.Dial("tcp", fmt.Sprintf("127.0.0.1:%d", cPort))
	require.NoError(t, err)
	defer proxyConn.Close()

	// Send HTTP CONNECT request
	connectReq := fmt.Sprintf("CONNECT 127.0.0.1:%d HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nUser-Agent: curl/8.0\r\n\r\n", targetPort, targetPort)
	_, err = proxyConn.Write([]byte(connectReq))
	require.NoError(t, err)

	// Read HTTP 200 Connection Established response
	bufReader := bufio.NewReader(proxyConn)
	statusLine, err := bufReader.ReadString('\n')
	require.NoError(t, err)
	assert.Contains(t, statusLine, "200 Connection Established")

	// Read empty line
	_, err = bufReader.ReadString('\n')
	require.NoError(t, err)

	// Send raw payload
	testMsg := "Hello HTTP Tunnel"
	_, err = proxyConn.Write([]byte(testMsg))
	require.NoError(t, err)

	readBuf := make([]byte, 1024)
	n, err := bufReader.Read(readBuf)
	require.NoError(t, err)
	assert.Equal(t, "HTTP_ECHO: "+testMsg, string(readBuf[:n]))
}

func TestEnginePlainHttpProxyFlow(t *testing.T) {
	// 1. Target Plain HTTP Echo Server
	targetListener, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	defer targetListener.Close()
	targetPort := targetListener.Addr().(*net.TCPAddr).Port

	go func() {
		conn, err := targetListener.Accept()
		if err != nil {
			return
		}
		defer conn.Close()
		buf := make([]byte, 1024)
		n, _ := conn.Read(buf)
		if n > 0 {
			resp := "HTTP/1.1 200 OK\r\nContent-Length: 13\r\n\r\nHello From Web"
			conn.Write([]byte(resp))
		}
	}()

	// 2. Start Engine
	sPort := getFreePort()
	cPort := getFreePort()
	eng := NewEngine(Config{
		ServerPort: sPort,
		ClientPort: cPort,
		ListenAddr: "127.0.0.1",
		Hostname:   "PlainHttpTester",
		Advertise:  "127.0.0.1",
	})
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	require.NoError(t, eng.Start(ctx))
	defer eng.Stop()

	// 3. Send absolute GET request to hybrid port
	proxyConn, err := net.Dial("tcp", fmt.Sprintf("127.0.0.1:%d", cPort))
	require.NoError(t, err)
	defer proxyConn.Close()

	getReq := fmt.Sprintf("GET http://127.0.0.1:%d/index.html HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nProxy-Connection: keep-alive\r\n\r\n", targetPort, targetPort)
	_, err = proxyConn.Write([]byte(getReq))
	require.NoError(t, err)

	bufReader := bufio.NewReader(proxyConn)
	statusLine, err := bufReader.ReadString('\n')
	require.NoError(t, err)
	assert.Contains(t, statusLine, "200 OK")
}

func TestEngineStrictRoundRobinDistribution(t *testing.T) {
	eng := NewEngine(Config{
		ServerPort: 0,
		ClientPort: getFreePort(),
		Hostname:   "RRTester",
	})

	// Add 2 remote nodes
	eng.UpdateNode(&Node{
		ID:       "node-A",
		Hostname: "NodeA",
		IP:       "192.168.1.1",
		Port:     10080,
		Status:   NodeStatusOnline,
	})
	eng.UpdateNode(&Node{
		ID:       "node-B",
		Hostname: "NodeB",
		IP:       "192.168.1.2",
		Port:     10080,
		Status:   NodeStatusOnline,
	})

	// Perform 10 selections and verify strict 1:1 alternating order: A, B, A, B, A, B...
	expectedOrder := []string{"node-A", "node-B", "node-A", "node-B", "node-A", "node-B", "node-A", "node-B", "node-A", "node-B"}
	for i, expectedID := range expectedOrder {
		selected, err := eng.selectNode()
		require.NoError(t, err)
		assert.Equal(t, expectedID, selected.ID, "Failed at iteration %d", i)
	}
}

func TestRemoteTargetConnectFailureFailConnsIncremented(t *testing.T) {
	// Pick an unused local port as non-existent target
	unreachablePort := getFreePort()

	sPort := getFreePort()
	cPort := getFreePort()
	eng := NewEngine(Config{
		ServerPort: sPort,
		ClientPort: cPort,
		ListenAddr: "127.0.0.1",
		Hostname:   "FailConnTester",
		Advertise:  "127.0.0.1",
	})
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	require.NoError(t, eng.Start(ctx))
	defer eng.Stop()

	// 1. SOCKS5 request to unreachable target
	proxyAddr := fmt.Sprintf("127.0.0.1:%d", cPort)
	conn, err := net.Dial("tcp", proxyAddr)
	require.NoError(t, err)

	_, _ = conn.Write([]byte{0x05, 0x01, 0x00})
	authResp := make([]byte, 2)
	_, _ = io.ReadFull(conn, authResp)

	// CONNECT to unreachable port
	req := []byte{0x05, 0x01, 0x00, 0x01, 127, 0, 0, 1, byte(unreachablePort >> 8), byte(unreachablePort & 0xff)}
	_, _ = conn.Write(req)

	socksResp := make([]byte, 10)
	_, _ = io.ReadFull(conn, socksResp)
	assert.NotEqual(t, byte(0x00), socksResp[1], "Expected SOCKS5 error response code")
	conn.Close()

	// 2. HTTP CONNECT request to unreachable target
	httpConn, err := net.Dial("tcp", proxyAddr)
	require.NoError(t, err)

	connectReq := fmt.Sprintf("CONNECT 127.0.0.1:%d HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n\r\n", unreachablePort, unreachablePort)
	_, _ = httpConn.Write([]byte(connectReq))

	bufReader := bufio.NewReader(httpConn)
	statusLine, err := bufReader.ReadString('\n')
	require.NoError(t, err)
	assert.Contains(t, statusLine, "502 Bad Gateway")
	httpConn.Close()

	// Verify FailConns is recorded
	nodes := eng.GetNodes()
	require.NotEmpty(t, nodes)
	var totalFail uint64
	for _, n := range nodes {
		totalFail += n.FailConns
	}
	assert.Greater(t, totalFail, uint64(0), "Expected FailConns > 0 for unreachable target")
}

func TestMultiNodeFailoverWhenRemoteOutboundFails(t *testing.T) {
	// 1. Start Echo Destination
	destListener, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	defer destListener.Close()
	destPort := destListener.Addr().(*net.TCPAddr).Port

	go func() {
		for {
			conn, err := destListener.Accept()
			if err != nil {
				return
			}
			go func(c net.Conn) {
				defer c.Close()
				buf := make([]byte, 1024)
				n, _ := c.Read(buf)
				if n > 0 {
					c.Write([]byte("ECHO_DEST: " + string(buf[:n])))
				}
			}(conn)
		}
	}()

	// 2. Start Faulty Server S1 (Always rejects outbound requests with 0x01)
	faultyS1Listener, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	defer faultyS1Listener.Close()
	s1Port := faultyS1Listener.Addr().(*net.TCPAddr).Port

	go func() {
		for {
			conn, err := faultyS1Listener.Accept()
			if err != nil {
				return
			}
			go func(c net.Conn) {
				defer c.Close()
				r := bufio.NewReader(c)
				_, _ = r.ReadBytes('\n') // read header
				_, _ = c.Write([]byte{0x01}) // reject
			}(conn)
		}
	}()

	// 3. Start Healthy Server S2
	s2Port := getFreePort()
	engS2 := NewEngine(Config{
		ServerPort: s2Port,
		ClientPort: 0,
		ListenAddr: "127.0.0.1",
		Hostname:   "Healthy-S2",
		Advertise:  "127.0.0.1",
	})
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	require.NoError(t, engS2.Start(ctx))
	defer engS2.Stop()

	// 4. Start Client Engine with S1 and S2
	clientPort := getFreePort()
	engClient := NewEngine(Config{
		ServerPort: 0,
		ClientPort: clientPort,
		ListenAddr: "127.0.0.1",
		Hostname:   "Client-Failover",
		Advertise:  "127.0.0.1",
	})
	require.NoError(t, engClient.Start(ctx))
	defer engClient.Stop()

	engClient.UpdateNode(&Node{
		ID:       "node-faulty-s1",
		Hostname: "FaultyS1",
		IP:       "127.0.0.1",
		Port:     s1Port,
		Status:   NodeStatusOnline,
	})
	engClient.UpdateNode(&Node{
		ID:       "node-healthy-s2",
		Hostname: "HealthyS2",
		IP:       "127.0.0.1",
		Port:     s2Port,
		Status:   NodeStatusOnline,
	})

	// 5. Connect through Client SOCKS5
	proxyConn, err := net.Dial("tcp", fmt.Sprintf("127.0.0.1:%d", clientPort))
	require.NoError(t, err)
	defer proxyConn.Close()

	_, _ = proxyConn.Write([]byte{0x05, 0x01, 0x00})
	authResp := make([]byte, 2)
	_, _ = io.ReadFull(proxyConn, authResp)

	req := []byte{0x05, 0x01, 0x00, 0x01, 127, 0, 0, 1, byte(destPort >> 8), byte(destPort & 0xff)}
	_, _ = proxyConn.Write(req)

	socksResp := make([]byte, 10)
	_, _ = io.ReadFull(proxyConn, socksResp)
	assert.Equal(t, byte(0x00), socksResp[1], "Client should succeed via failover to healthy S2")

	_, _ = proxyConn.Write([]byte("PingFailover"))
	readBuf := make([]byte, 1024)
	n, err := proxyConn.Read(readBuf)
	require.NoError(t, err)
	assert.Equal(t, "ECHO_DEST: PingFailover", string(readBuf[:n]))

	// S1 should have recorded FailConns
	nodes := engClient.GetNodes()
	for _, n := range nodes {
		if n.ID == "node-faulty-s1" {
			assert.GreaterOrEqual(t, n.FailConns, uint64(1))
		}
	}
}




