package mops

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestEndToEndMultiNodeLoadBalancing(t *testing.T) {
	// 1. Start Echo Destination Server
	destListener, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	defer destListener.Close()

	destAddr := destListener.Addr().String()

	var destHits int64
	go func() {
		for {
			conn, err := destListener.Accept()
			if err != nil {
				return
			}
			atomic.AddInt64(&destHits, 1)
			go func(c net.Conn) {
				defer c.Close()
				buf := make([]byte, 1024)
				n, _ := c.Read(buf)
				if n > 0 {
					c.Write([]byte("RESPONSE: " + string(buf[:n])))
				}
			}(conn)
		}
	}()

	// 2. Start Server Node 1
	s1Port := getFreePort()
	cfgS1 := Config{
		ServerPort: s1Port,
		ClientPort: 0,
		ListenAddr: "127.0.0.1",
		Hostname:   "Server-01",
		Advertise:  "127.0.0.1",
	}
	engS1 := NewEngine(cfgS1)
	ctx := context.Background()
	require.NoError(t, engS1.Start(ctx))
	defer engS1.Stop()

	// 3. Start Server Node 2
	s2Port := getFreePort()
	cfgS2 := Config{
		ServerPort: s2Port,
		ClientPort: 0,
		ListenAddr: "127.0.0.1",
		Hostname:   "Server-02",
		Advertise:  "127.0.0.1",
	}
	engS2 := NewEngine(cfgS2)
	require.NoError(t, engS2.Start(ctx))
	defer engS2.Stop()

	// 4. Start Client Node (Connecting to S1 & S2)
	clientPort := getFreePort()
	cfgClient := Config{
		ServerPort: 0,
		ClientPort: clientPort,
		ListenAddr: "127.0.0.1",
		Hostname:   "Client-Me",
		Advertise:  "127.0.0.1",
	}
	engClient := NewEngine(cfgClient)
	require.NoError(t, engClient.Start(ctx))
	defer engClient.Stop()

	// Add S1 and S2 to Client Node Pool
	engClient.UpdateNode(&Node{
		ID:       "s1",
		Hostname: "Server-01",
		IP:       "127.0.0.1",
		Port:     s1Port,
		Role:     "Server",
		Status:   "ONLINE",
	})
	engClient.UpdateNode(&Node{
		ID:       "s2",
		Hostname: "Server-02",
		IP:       "127.0.0.1",
		Port:     s2Port,
		Role:     "Server",
		Status:   "ONLINE",
	})

	time.Sleep(100 * time.Millisecond)

	// 5. Send Concurrent Requests via SOCKS5 Proxy
	numRequests := 4
	var wg sync.WaitGroup

	_, destPortStr, _ := net.SplitHostPort(destAddr)
	destPort := 0
	fmt.Sscanf(destPortStr, "%d", &destPort)

	for i := 0; i < numRequests; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()

			proxyConn, err := net.Dial("tcp", fmt.Sprintf("127.0.0.1:%d", clientPort))
			if !assert.NoError(t, err) {
				return
			}

			// SOCKS5 Auth
			proxyConn.Write([]byte{0x05, 0x01, 0x00})
			authResp := make([]byte, 2)
			io.ReadFull(proxyConn, authResp)

			// SOCKS5 Connect
			req := []byte{0x05, 0x01, 0x00, 0x01, 127, 0, 0, 1, byte(destPort >> 8), byte(destPort & 0xff)}
			proxyConn.Write(req)
			resp := make([]byte, 10)
			io.ReadFull(proxyConn, resp)
			if !assert.Equal(t, byte(0x00), resp[1]) {
				return
			}

			// Send Data
			msg := fmt.Sprintf("Req #%d", idx)
			proxyConn.Write([]byte(msg))

			readBuf := make([]byte, 1024)
			n, err := proxyConn.Read(readBuf)
			assert.NoError(t, err)
			assert.Equal(t, "RESPONSE: "+msg, string(readBuf[:n]))
			proxyConn.Close()
		}(i)
	}

	wg.Wait()

	// Verify all requests succeeded
	assert.Equal(t, int64(numRequests), atomic.LoadInt64(&destHits))

	// Verify node traffic counters updated
	nodes := engClient.GetNodes()
	var totalBytes uint64
	for _, n := range nodes {
		totalBytes += n.BytesUp + n.BytesDown
	}
	assert.Greater(t, totalBytes, uint64(0))

	// 6. Test Real Node Shutdown & Automatic Failover
	// Stop engS1 unexpectedly (without manual RemoveNode)
	engS1.Stop()

	// Send requests to ensure round-robin hits the closed node s1, marking it OFFLINE
	for i := 0; i < 5; i++ {
		proxyConn, err := net.Dial("tcp", fmt.Sprintf("127.0.0.1:%d", clientPort))
		if err != nil {
			continue
		}
		proxyConn.Write([]byte{0x05, 0x01, 0x00})
		authResp := make([]byte, 2)
		io.ReadFull(proxyConn, authResp)

		req := []byte{0x05, 0x01, 0x00, 0x01, 127, 0, 0, 1, byte(destPort >> 8), byte(destPort & 0xff)}
		proxyConn.Write(req)
		resp := make([]byte, 10)
		io.ReadFull(proxyConn, resp)

		if resp[1] == 0x00 {
			proxyConn.Write([]byte("AutoFailoverReq"))
			readBuf := make([]byte, 1024)
			n, err := proxyConn.Read(readBuf)
			if err == nil && n > 0 {
				assert.Equal(t, "RESPONSE: AutoFailoverReq", string(readBuf[:n]))
			}
		}
		proxyConn.Close()
	}

	// Verify s1 is now automatically OFFLINE in Client's pool
	require.Eventually(t, func() bool {
		nodes := engClient.GetNodes()
		for _, n := range nodes {
			if n.ID == "s1" {
				return n.Status == "OFFLINE"
			}
		}
		return false
	}, 1*time.Second, 20*time.Millisecond)
}

func TestEndToEndLargeDataStream(t *testing.T) {
	// 1. Target Echo Server accepting large stream
	destListener, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	defer destListener.Close()

	destAddr := destListener.Addr().String()
	_, destPortStr, _ := net.SplitHostPort(destAddr)
	destPort := 0
	fmt.Sscanf(destPortStr, "%d", &destPort)

	go func() {
		conn, err := destListener.Accept()
		if err != nil {
			return
		}
		defer conn.Close()
		io.Copy(conn, conn) // Mirror back all stream data
	}()

	// 2. Server Node
	sPort := getFreePort()
	cfgS := Config{
		ServerPort: sPort,
		ClientPort: 0,
		ListenAddr: "127.0.0.1",
		Hostname:   "BigStreamServer",
		Advertise:  "127.0.0.1",
	}
	engS := NewEngine(cfgS)
	ctx := context.Background()
	require.NoError(t, engS.Start(ctx))
	defer engS.Stop()

	// 3. Client Node
	cPort := getFreePort()
	cfgC := Config{
		ServerPort: 0,
		ClientPort: cPort,
		ListenAddr: "127.0.0.1",
		Hostname:   "BigStreamClient",
		Advertise:  "127.0.0.1",
	}
	engC := NewEngine(cfgC)
	require.NoError(t, engC.Start(ctx))
	defer engC.Stop()

	engC.UpdateNode(&Node{
		ID:       "big-s1",
		Hostname: "BigStreamServer",
		IP:       "127.0.0.1",
		Port:     sPort,
		Role:     "Server",
		Status:   "ONLINE",
	})

	// 4. Dial SOCKS5 Proxy & Stream 500 KB Data
	proxyConn, err := net.Dial("tcp", fmt.Sprintf("127.0.0.1:%d", cPort))
	require.NoError(t, err)
	defer proxyConn.Close()

	proxyConn.Write([]byte{0x05, 0x01, 0x00})
	authResp := make([]byte, 2)
	io.ReadFull(proxyConn, authResp)

	req := []byte{0x05, 0x01, 0x00, 0x01, 127, 0, 0, 1, byte(destPort >> 8), byte(destPort & 0xff)}
	proxyConn.Write(req)
	resp := make([]byte, 10)
	io.ReadFull(proxyConn, resp)
	require.Equal(t, byte(0x00), resp[1])

	// Send 500 KB payload
	payloadSize := 500 * 1024
	sendData := make([]byte, payloadSize)
	for i := range sendData {
		sendData[i] = byte(i % 256)
	}

	recvData := make([]byte, payloadSize)
	var wg sync.WaitGroup
	wg.Add(2)

	go func() {
		defer wg.Done()
		proxyConn.Write(sendData)
	}()

	go func() {
		defer wg.Done()
		io.ReadFull(proxyConn, recvData)
	}()

	wg.Wait()
	assert.Equal(t, sendData, recvData)

	// Verify stats
	up, down := engC.GetSpeed()
	assert.GreaterOrEqual(t, up, float64(0))
	assert.GreaterOrEqual(t, down, float64(0))
}

func TestEndToEndMultiNodeFileTransfer(t *testing.T) {
	// 1. Create temporary download dir for Server Node B
	tempDir, err := os.MkdirTemp("", "mops_e2e_download_*")
	require.NoError(t, err)
	defer os.RemoveAll(tempDir)

	// 2. Start Receiver Server Node B
	sPortB := getFreePort()
	cfgB := Config{
		ServerPort:  sPortB,
		ClientPort:  0,
		ListenAddr:  "127.0.0.1",
		Hostname:    "Server-NodeB",
		DownloadDir: tempDir,
	}
	engB := NewEngine(cfgB)
	ctx := context.Background()
	require.NoError(t, engB.Start(ctx))
	defer engB.Stop()

	// 3. Start Sender Controller Node A with REST API
	apiPortA := getFreePort()
	cfgA := Config{
		ServerPort: 0,
		ClientPort: 0,
		APIPort:    apiPortA,
		ListenAddr: "127.0.0.1",
		Hostname:   "Controller-NodeA",
	}
	engA := NewEngine(cfgA)
	require.NoError(t, engA.Start(ctx))
	defer engA.Stop()

	time.Sleep(100 * time.Millisecond)

	// 4. Create Source File on Node A machine (2MB payload)
	srcFile, err := os.CreateTemp("", "mops_e2e_source_*.bin")
	require.NoError(t, err)
	defer os.Remove(srcFile.Name())

	payloadSize := 2 * 1024 * 1024
	sendBytes := make([]byte, payloadSize)
	for i := range sendBytes {
		sendBytes[i] = byte((i * 17) % 256)
	}
	_, err = srcFile.Write(sendBytes)
	require.NoError(t, err)
	srcFile.Close()

	hasher := sha256.New()
	hasher.Write(sendBytes)
	expectedHash := fmt.Sprintf("sha256:%s", hex.EncodeToString(hasher.Sum(nil)))

	// 5. Call Node A REST API to transfer to Node B
	transferUrl := fmt.Sprintf("http://127.0.0.1:%d/api/v1/files/transfer?target_ip=127.0.0.1&target_port=%d&path=%s", apiPortA, sPortB, srcFile.Name())
	req, err := http.NewRequest(http.MethodPost, transferUrl, nil)
	require.NoError(t, err)

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	require.NoError(t, err)
	defer resp.Body.Close()

	require.Equal(t, http.StatusOK, resp.StatusCode)

	var apiResp APIResponse
	err = json.NewDecoder(resp.Body).Decode(&apiResp)
	require.NoError(t, err)
	require.Equal(t, 200, apiResp.Code)

	// 6. Verify Node B DownloadDir received the file accurately with Trailer Hash
	expectedFileName := filepath.Base(srcFile.Name())
	destFilePath := filepath.Join(tempDir, expectedFileName)

	require.Eventually(t, func() bool {
		fi, err := os.Stat(destFilePath)
		return err == nil && fi.Size() == int64(len(sendBytes))
	}, 3*time.Second, 50*time.Millisecond)

	recvBytes, err := os.ReadFile(destFilePath)
	require.NoError(t, err)
	require.Equal(t, sendBytes, recvBytes)

	dataMap, ok := apiResp.Data.(map[string]interface{})
	require.True(t, ok)
	assert.Equal(t, expectedHash, dataMap["file_hash"])
}

func TestEndToEndCurlHttpAndSocks5Proxy(t *testing.T) {
	// 1. Target HTTP Web Server
	destListener, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	defer destListener.Close()

	destPort := destListener.Addr().(*net.TCPAddr).Port

	var s1Hits, s2Hits int64

	go func() {
		for {
			conn, err := destListener.Accept()
			if err != nil {
				return
			}
			go func(c net.Conn) {
				defer c.Close()
				buf := make([]byte, 2048)
				n, _ := c.Read(buf)
				if n > 0 {
					resp := "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 12\r\n\r\nHello Client"
					c.Write([]byte(resp))
				}
			}(conn)
		}
	}()

	// 2. Server 1 & Server 2 Nodes
	s1Port := getFreePort()
	engS1 := NewEngine(Config{ServerPort: s1Port, ClientPort: 0, Hostname: "S1", Advertise: "127.0.0.1"})
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	require.NoError(t, engS1.Start(ctx))
	defer engS1.Stop()

	s2Port := getFreePort()
	engS2 := NewEngine(Config{ServerPort: s2Port, ClientPort: 0, Hostname: "S2", Advertise: "127.0.0.1"})
	require.NoError(t, engS2.Start(ctx))
	defer engS2.Stop()

	// 3. Client Node with hybrid 10081 port
	cPort := getFreePort()
	engClient := NewEngine(Config{ServerPort: 0, ClientPort: cPort, Hostname: "ClientNode", Advertise: "127.0.0.1"})
	require.NoError(t, engClient.Start(ctx))
	defer engClient.Stop()

	engClient.UpdateNode(&Node{ID: "node-s1", Hostname: "S1", IP: "127.0.0.1", Port: s1Port, Status: NodeStatusOnline})
	engClient.UpdateNode(&Node{ID: "node-s2", Hostname: "S2", IP: "127.0.0.1", Port: s2Port, Status: NodeStatusOnline})

	// 4. Test HTTP Client using HTTP Proxy URL (equivalent to curl -x http://127.0.0.1:cPort)
	proxyURL, err := url.Parse(fmt.Sprintf("http://127.0.0.1:%d", cPort))
	require.NoError(t, err)

	httpClient := &http.Client{
		Transport: &http.Transport{
			Proxy: http.ProxyURL(proxyURL),
		},
		Timeout: 3 * time.Second,
	}

	// Send 6 HTTP requests through proxy
	for i := 0; i < 6; i++ {
		resp, err := httpClient.Get(fmt.Sprintf("http://127.0.0.1:%d/test", destPort))
		require.NoError(t, err)
		body, _ := io.ReadAll(resp.Body)
		resp.Body.Close()
		assert.Equal(t, "Hello Client", string(body))
	}

	// Verify both servers processed requests evenly (3 each out of 6)
	nodes := engClient.GetNodes()
	for _, n := range nodes {
		if n.ID == "node-s1" {
			s1Hits = int64(n.SuccessConns)
		}
		if n.ID == "node-s2" {
			s2Hits = int64(n.SuccessConns)
		}
	}
	assert.Equal(t, int64(3), s1Hits, "Server 1 should have received exactly 3 requests")
	assert.Equal(t, int64(3), s2Hits, "Server 2 should have received exactly 3 requests")
}

