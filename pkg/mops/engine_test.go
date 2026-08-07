package mops

import (
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
	time.Sleep(100 * time.Millisecond)
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


