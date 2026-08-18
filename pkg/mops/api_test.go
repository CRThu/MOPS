package mops

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestGETNodesAPI(t *testing.T) {
	apiPort := 10830
	cfg := Config{
		ServerPort: 10831,
		ClientPort: 10832,
		APIPort:    apiPort,
		Hostname:   "TestNode-API",
		Strategy:   "random",
	}

	engine := NewEngine(cfg)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	if err := engine.Start(ctx); err != nil {
		t.Fatalf("failed to start engine: %v", err)
	}
	defer engine.Stop()

	// Wait for server to bind
	time.Sleep(100 * time.Millisecond)

	// 1. Test GET /api/v1/nodes
	url := fmt.Sprintf("http://127.0.0.1:%d/api/v1/nodes", apiPort)
	resp, err := http.Get(url)
	if err != nil {
		t.Fatalf("failed to perform GET /api/v1/nodes: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Errorf("expected status 200, got %d", resp.StatusCode)
	}

	var apiResp struct {
		Code    int     `json:"code"`
		Message string  `json:"message"`
		Total   int     `json:"total"`
		Data    []*Node `json:"data"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&apiResp); err != nil {
		t.Fatalf("failed to decode JSON response: %v", err)
	}

	if apiResp.Code != 200 {
		t.Errorf("expected code 200, got %d", apiResp.Code)
	}
	if apiResp.Total < 1 {
		t.Errorf("expected total >= 1, got %d", apiResp.Total)
	}
	if len(apiResp.Data) == 0 {
		t.Errorf("expected non-empty node slice")
	} else if apiResp.Data[0].Hostname != "TestNode-API" {
		t.Errorf("expected hostname TestNode-API, got %s", apiResp.Data[0].Hostname)
	}

	// 2. Test Invalid Method (POST)
	postResp, err := http.Post(url, "application/json", nil)
	if err != nil {
		t.Fatalf("failed to perform POST /api/v1/nodes: %v", err)
	}
	defer postResp.Body.Close()

	if postResp.StatusCode != http.StatusMethodNotAllowed {
		t.Errorf("expected status 405 Method Not Allowed, got %d", postResp.StatusCode)
	}
}

func TestGETStatusAPI(t *testing.T) {
	apiPort := 10833
	cfg := Config{
		ServerPort: 10834,
		ClientPort: 10835,
		APIPort:    apiPort,
		Hostname:   "TestStatusNode",
		Strategy:   "hash",
	}

	engine := NewEngine(cfg)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	if err := engine.Start(ctx); err != nil {
		t.Fatalf("failed to start engine: %v", err)
	}
	defer engine.Stop()

	time.Sleep(100 * time.Millisecond)

	url := fmt.Sprintf("http://127.0.0.1:%d/api/v1/status", apiPort)
	resp, err := http.Get(url)
	if err != nil {
		t.Fatalf("failed to GET /api/v1/status: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Errorf("expected status 200, got %d", resp.StatusCode)
	}

	var apiResp struct {
		Code    int        `json:"code"`
		Message string     `json:"message"`
		Data    StatusData `json:"data"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&apiResp); err != nil {
		t.Fatalf("failed to decode status response: %v", err)
	}

	if apiResp.Code != 200 {
		t.Errorf("expected code 200, got %d", apiResp.Code)
	}
	if apiResp.Data.Hostname != "TestStatusNode" {
		t.Errorf("expected hostname TestStatusNode, got %s", apiResp.Data.Hostname)
	}
	if apiResp.Data.APIPort != apiPort {
		t.Errorf("expected apiPort %d, got %d", apiPort, apiResp.Data.APIPort)
	}
	if apiResp.Data.Strategy != "hash" {
		t.Errorf("expected strategy hash, got %s", apiResp.Data.Strategy)
	}
}

func TestAPIServerLifecycle(t *testing.T) {
	apiPort := 10836
	cfg := Config{
		ServerPort: 10837,
		ClientPort: 10838,
		APIPort:    apiPort,
		Hostname:   "LifecycleNode",
	}

	engine := NewEngine(cfg)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	if err := engine.Start(ctx); err != nil {
		t.Fatalf("engine start failed: %v", err)
	}

	// Verify server is listening
	url := fmt.Sprintf("http://127.0.0.1:%d/api/v1/status", apiPort)
	resp, err := http.Get(url)
	if err != nil {
		t.Fatalf("expected server reachable, got: %v", err)
	}
	resp.Body.Close()

	// Stop Engine
	engine.Stop()
	time.Sleep(100 * time.Millisecond)

	// Verify server is no longer reachable
	_, err = http.Get(url)
	if err == nil {
		t.Errorf("expected error after engine stop, but API still responded")
	}
}

func TestAPIFileTransfer(t *testing.T) {
	tempDir, err := os.MkdirTemp("", "mops_api_file_*")
	if err != nil {
		t.Fatalf("failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tempDir)

	serverPort := 10840
	apiPort := 10841

	cfg := Config{
		ServerPort:  serverPort,
		ClientPort:  0,
		APIPort:     apiPort,
		Hostname:    "APITransferTarget",
		DownloadDir: tempDir,
	}

	engine := NewEngine(cfg)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	if err := engine.Start(ctx); err != nil {
		t.Fatalf("engine start failed: %v", err)
	}
	defer engine.Stop()

	time.Sleep(100 * time.Millisecond)

	// 1. Create a dummy local file for ?path= test
	srcFile, err := os.CreateTemp("", "mops_src_file_*.txt")
	require.NoError(t, err)
	defer os.Remove(srcFile.Name())
	srcContent := []byte("Auto path calculation test content")
	_, err = srcFile.Write(srcContent)
	require.NoError(t, err)
	srcFile.Close()

	// 2. Call POST /api/v1/files/transfer with ?path= parameter
	pathUrl := fmt.Sprintf("http://127.0.0.1:%d/api/v1/files/transfer?target_ip=127.0.0.1&target_port=%d&path=%s", apiPort, serverPort, srcFile.Name())
	reqPath, err := http.NewRequest(http.MethodPost, pathUrl, nil)
	require.NoError(t, err)

	client := &http.Client{Timeout: 5 * time.Second}
	resp, err := client.Do(reqPath)
	require.NoError(t, err)
	defer resp.Body.Close()

	require.Equal(t, http.StatusOK, resp.StatusCode)

	var apiResp APIResponse
	err = json.NewDecoder(resp.Body).Decode(&apiResp)
	require.NoError(t, err)
	require.Equal(t, 200, apiResp.Code)

	// Verify file saved in download dir with automatically extracted name
	expectedName := filepath.Base(srcFile.Name())
	targetPath := filepath.Join(tempDir, expectedName)
	require.Eventually(t, func() bool {
		info, err := os.Stat(targetPath)
		return err == nil && info.Size() == int64(len(srcContent))
	}, 2*time.Second, 20*time.Millisecond)

	readData, err := os.ReadFile(targetPath)
	require.NoError(t, err)
	require.Equal(t, srcContent, readData)
}

func TestAPIFileTransferNotFound(t *testing.T) {
	apiPort := 10842
	serverPort := 10843

	cfg := Config{
		ServerPort: serverPort,
		ClientPort: 0,
		APIPort:    apiPort,
		Hostname:   "NotFoundTest",
	}

	engine := NewEngine(cfg)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	require.NoError(t, engine.Start(ctx))
	defer engine.Stop()

	time.Sleep(100 * time.Millisecond)

	// Call POST with non-existent file path
	url := fmt.Sprintf("http://127.0.0.1:%d/api/v1/files/transfer?target_ip=127.0.0.1&target_port=%d&path=D:/non_existent_file_xyz.txt", apiPort, serverPort)
	req, err := http.NewRequest(http.MethodPost, url, nil)
	require.NoError(t, err)

	client := &http.Client{Timeout: 5 * time.Second}
	resp, err := client.Do(req)
	require.NoError(t, err)
	defer resp.Body.Close()

	require.Equal(t, http.StatusBadRequest, resp.StatusCode)

	var apiResp APIResponse
	err = json.NewDecoder(resp.Body).Decode(&apiResp)
	require.NoError(t, err)
	require.Equal(t, 400, apiResp.Code)
}

func TestAPISystemProxy(t *testing.T) {
	origInfo, _ := GetSystemProxyInfo()
	defer func() {
		_ = RestoreSystemProxyInfo(origInfo)
	}()

	apiPort := 10845
	cfg := Config{
		ServerPort: 10846,
		ClientPort: 10847,
		APIPort:    apiPort,
		Hostname:   "ProxyAPINode",
	}

	engine := NewEngine(cfg)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	require.NoError(t, engine.Start(ctx))
	defer engine.Stop()

	time.Sleep(100 * time.Millisecond)

	// GET /api/v1/system-proxy
	getURL := fmt.Sprintf("http://127.0.0.1:%d/api/v1/system-proxy", apiPort)
	resp, err := http.Get(getURL)
	require.NoError(t, err)
	require.Equal(t, http.StatusOK, resp.StatusCode)
	resp.Body.Close()

	// POST /api/v1/system-proxy (action: set custom address)
	postBody, _ := json.Marshal(map[string]interface{}{
		"action":     "set",
		"proxy_addr": "127.0.0.1:7890",
	})
	respPost, err := http.Post(getURL, "application/json", bytes.NewReader(postBody))
	require.NoError(t, err)
	require.Equal(t, http.StatusOK, respPost.StatusCode)

	var setResp struct {
		Code int             `json:"code"`
		Data SystemProxyInfo `json:"data"`
	}
	require.NoError(t, json.NewDecoder(respPost.Body).Decode(&setResp))
	respPost.Body.Close()
	assert.True(t, setResp.Data.Enabled)
	assert.Equal(t, "127.0.0.1:7890", setResp.Data.ProxyServer)
	assert.Equal(t, "http://127.0.0.1:7890", setResp.Data.HttpProxy)

	// POST /api/v1/system-proxy (action: clear)
	postClear, _ := json.Marshal(map[string]interface{}{
		"action": "clear",
	})
	respClear, err := http.Post(getURL, "application/json", bytes.NewReader(postClear))
	require.NoError(t, err)
	require.Equal(t, http.StatusOK, respClear.StatusCode)

	var clearResp struct {
		Code int             `json:"code"`
		Data SystemProxyInfo `json:"data"`
	}
	require.NoError(t, json.NewDecoder(respClear.Body).Decode(&clearResp))
	respClear.Body.Close()
	assert.False(t, clearResp.Data.Enabled)
	assert.Empty(t, clearResp.Data.HttpProxy)
}

func TestAPIClientControl(t *testing.T) {
	apiPort := 10850
	clientPort := 10851
	cfg := Config{
		ServerPort: 10852,
		ClientPort: clientPort,
		APIPort:    apiPort,
		Hostname:   "ClientControlNode",
	}

	engine := NewEngine(cfg)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	require.NoError(t, engine.Start(ctx))
	defer engine.Stop()

	time.Sleep(100 * time.Millisecond)

	url := fmt.Sprintf("http://127.0.0.1:%d/api/v1/client", apiPort)

	// 1. GET status
	resp, err := http.Get(url)
	require.NoError(t, err)
	require.Equal(t, http.StatusOK, resp.StatusCode)
	resp.Body.Close()

	// 2. Stop Client via POST
	stopBody, _ := json.Marshal(map[string]interface{}{"enable": false})
	respStop, err := http.Post(url, "application/json", bytes.NewReader(stopBody))
	require.NoError(t, err)
	require.Equal(t, http.StatusOK, respStop.StatusCode)
	respStop.Body.Close()
	require.False(t, engine.GetClientEnabled())

	// 3. Start Client via POST
	startBody, _ := json.Marshal(map[string]interface{}{"enable": true})
	respStart, err := http.Post(url, "application/json", bytes.NewReader(startBody))
	require.NoError(t, err)
	require.Equal(t, http.StatusOK, respStart.StatusCode)
	respStart.Body.Close()
	require.True(t, engine.GetClientEnabled())
}

func TestAPIServerControl(t *testing.T) {
	apiPort := 10855
	serverPort := 10856
	cfg := Config{
		ServerPort: serverPort,
		ClientPort: 10857,
		APIPort:    apiPort,
		Hostname:   "ServerControlNode",
	}

	engine := NewEngine(cfg)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	require.NoError(t, engine.Start(ctx))
	defer engine.Stop()

	time.Sleep(100 * time.Millisecond)

	url := fmt.Sprintf("http://127.0.0.1:%d/api/v1/server", apiPort)

	// 1. GET status
	resp, err := http.Get(url)
	require.NoError(t, err)
	require.Equal(t, http.StatusOK, resp.StatusCode)
	resp.Body.Close()

	// 2. Stop Server via POST
	stopBody, _ := json.Marshal(map[string]interface{}{"enable": false})
	respStop, err := http.Post(url, "application/json", bytes.NewReader(stopBody))
	require.NoError(t, err)
	require.Equal(t, http.StatusOK, respStop.StatusCode)
	respStop.Body.Close()
	require.False(t, engine.GetServerEnabled())

	// 3. Start Server via POST
	startBody, _ := json.Marshal(map[string]interface{}{"enable": true})
	respStart, err := http.Post(url, "application/json", bytes.NewReader(startBody))
	require.NoError(t, err)
	require.Equal(t, http.StatusOK, respStart.StatusCode)
	respStart.Body.Close()
	require.True(t, engine.GetServerEnabled())
}

func TestAPIInvalidBodyAndMethod(t *testing.T) {
	apiPort := 10858
	cfg := Config{
		ServerPort: 10859,
		ClientPort: 10860,
		APIPort:    apiPort,
	}

	engine := NewEngine(cfg)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	require.NoError(t, engine.Start(ctx))
	defer engine.Stop()

	time.Sleep(100 * time.Millisecond)

	endpoints := []string{"system-proxy", "client", "server"}
	client := &http.Client{Timeout: 2 * time.Second}

	for _, ep := range endpoints {
		url := fmt.Sprintf("http://127.0.0.1:%d/api/v1/%s", apiPort, ep)

		// Invalid JSON POST body -> 400
		respBad, err := client.Post(url, "application/json", bytes.NewBufferString("{invalid_json}"))
		require.NoError(t, err)
		assert.Equal(t, http.StatusBadRequest, respBad.StatusCode)
		respBad.Body.Close()

		// Method Not Allowed (DELETE) -> 405
		reqDel, err := http.NewRequest(http.MethodDelete, url, nil)
		require.NoError(t, err)
		respDel, err := client.Do(reqDel)
		require.NoError(t, err)
		assert.Equal(t, http.StatusMethodNotAllowed, respDel.StatusCode)
		respDel.Body.Close()
	}
}

func TestAPIConfigProgressAndService(t *testing.T) {
	apiPort := 10860
	cfg := Config{
		ServerPort:  10861,
		ClientPort:  10862,
		APIPort:     apiPort,
		Hostname:    "ConfigTestNode",
		DownloadDir: "./original_dir",
	}

	engine := NewEngine(cfg)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	require.NoError(t, engine.Start(ctx))
	defer engine.Stop()

	time.Sleep(100 * time.Millisecond)

	client := &http.Client{Timeout: 3 * time.Second}

	// 1. GET /api/v1/config
	resp, err := client.Get(fmt.Sprintf("http://127.0.0.1:%d/api/v1/config", apiPort))
	require.NoError(t, err)
	assert.Equal(t, http.StatusOK, resp.StatusCode)
	var cfgResp APIResponse
	require.NoError(t, json.NewDecoder(resp.Body).Decode(&cfgResp))
	resp.Body.Close()
	assert.Equal(t, 200, cfgResp.Code)

	// 2. POST /api/v1/config (Update download_dir and advertise)
	newDir := filepath.Join(os.TempDir(), "mops_api_download_test")
	defer os.RemoveAll(newDir)

	postBody, _ := json.Marshal(map[string]string{"download_dir": newDir, "advertise": "192.168.1.222"})
	resp, err = client.Post(fmt.Sprintf("http://127.0.0.1:%d/api/v1/config", apiPort), "application/json", bytes.NewBuffer(postBody))
	require.NoError(t, err)
	assert.Equal(t, http.StatusOK, resp.StatusCode)
	resp.Body.Close()
	assert.Equal(t, newDir, engine.GetDownloadDir())
	assert.Equal(t, "192.168.1.222", engine.GetAdvertise())

	// 2b. GET /api/v1/interfaces
	resp, err = client.Get(fmt.Sprintf("http://127.0.0.1:%d/api/v1/interfaces", apiPort))
	require.NoError(t, err)
	assert.Equal(t, http.StatusOK, resp.StatusCode)
	var ifacesResp APIResponse
	require.NoError(t, json.NewDecoder(resp.Body).Decode(&ifacesResp))
	resp.Body.Close()
	assert.Equal(t, 200, ifacesResp.Code)

	// 3. GET /api/v1/files/progress
	resp, err = client.Get(fmt.Sprintf("http://127.0.0.1:%d/api/v1/files/progress", apiPort))
	require.NoError(t, err)
	assert.Equal(t, http.StatusOK, resp.StatusCode)
	var progResp APIResponse
	require.NoError(t, json.NewDecoder(resp.Body).Decode(&progResp))
	resp.Body.Close()
	assert.Equal(t, 200, progResp.Code)

	// 4. GET /api/v1/service
	resp, err = client.Get(fmt.Sprintf("http://127.0.0.1:%d/api/v1/service", apiPort))
	require.NoError(t, err)
	assert.Equal(t, http.StatusOK, resp.StatusCode)
	var svcResp APIResponse
	require.NoError(t, json.NewDecoder(resp.Body).Decode(&svcResp))
	resp.Body.Close()
	assert.Equal(t, 200, svcResp.Code)

	// 5. POST /api/v1/service (Invalid Action -> 400 Bad Request)
	badBody, _ := json.Marshal(map[string]string{"action": "invalid_action_xyz"})
	resp, err = client.Post(fmt.Sprintf("http://127.0.0.1:%d/api/v1/service", apiPort), "application/json", bytes.NewBuffer(badBody))
	require.NoError(t, err)
	assert.Equal(t, http.StatusBadRequest, resp.StatusCode)
	resp.Body.Close()
}

func TestAPILaunchBrowser(t *testing.T) {
	apiPort := getFreePort()
	cfg := Config{
		ServerPort: 0,
		ClientPort: getFreePort(),
		APIPort:    apiPort,
		Hostname:   "BrowserTestNode",
	}

	engine := NewEngine(cfg)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	require.NoError(t, engine.Start(ctx))
	defer engine.Stop()

	client := &http.Client{Timeout: 5 * time.Second}

	// 1. GET /api/v1/status check has_chrome field
	statusResp, err := client.Get(fmt.Sprintf("http://127.0.0.1:%d/api/v1/status", apiPort))
	require.NoError(t, err)
	var sResp APIResponse
	require.NoError(t, json.NewDecoder(statusResp.Body).Decode(&sResp))
	statusResp.Body.Close()
	assert.Equal(t, 200, sResp.Code)

	// 2. GET /api/v1/browser/launch -> Method Not Allowed (405)
	getResp, err := client.Get(fmt.Sprintf("http://127.0.0.1:%d/api/v1/browser/launch", apiPort))
	require.NoError(t, err)
	assert.Equal(t, http.StatusMethodNotAllowed, getResp.StatusCode)
	getResp.Body.Close()

	// 3. POST /api/v1/browser/launch
	postResp, err := client.Post(fmt.Sprintf("http://127.0.0.1:%d/api/v1/browser/launch", apiPort), "application/json", nil)
	require.NoError(t, err)
	var launchResp APIResponse
	require.NoError(t, json.NewDecoder(postResp.Body).Decode(&launchResp))
	postResp.Body.Close()
	// If Chrome is installed on system, 200; if not, 404
	if FindChromePath() != "" {
		assert.Equal(t, 200, launchResp.Code)
	} else {
		assert.Equal(t, 404, launchResp.Code)
	}
}

func TestAPIOpenDownloadDir(t *testing.T) {
	tempDir := t.TempDir()
	apiPort := getFreePort()
	cfg := Config{
		ServerPort:  0,
		ClientPort:  0,
		APIPort:     apiPort,
		Hostname:    "OpenDirTestNode",
		DownloadDir: tempDir,
	}

	engine := NewEngine(cfg)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	require.NoError(t, engine.Start(ctx))
	defer engine.Stop()

	client := &http.Client{Timeout: 5 * time.Second}

	// 1. POST /api/v1/files/open-dir
	postResp, err := client.Post(fmt.Sprintf("http://127.0.0.1:%d/api/v1/files/open-dir", apiPort), "application/json", nil)
	require.NoError(t, err)
	var openResp struct {
		Code    int    `json:"code"`
		Message string `json:"message"`
		Data    struct {
			Path string `json:"path"`
		} `json:"data"`
	}
	require.NoError(t, json.NewDecoder(postResp.Body).Decode(&openResp))
	postResp.Body.Close()
	assert.Equal(t, 200, openResp.Code)
	assert.Contains(t, openResp.Data.Path, filepath.Base(tempDir))

	// 2. GET /api/v1/files/open-dir
	getResp, err := client.Get(fmt.Sprintf("http://127.0.0.1:%d/api/v1/files/open-dir", apiPort))
	require.NoError(t, err)
	assert.Equal(t, 200, getResp.StatusCode)
	getResp.Body.Close()

	// 3. DELETE /api/v1/files/open-dir -> 405 Method Not Allowed
	req, _ := http.NewRequest(http.MethodDelete, fmt.Sprintf("http://127.0.0.1:%d/api/v1/files/open-dir", apiPort), nil)
	delResp, err := client.Do(req)
	require.NoError(t, err)
	assert.Equal(t, http.StatusMethodNotAllowed, delResp.StatusCode)
	delResp.Body.Close()
}

func TestAPIConfigPersistenceAndEngineReload(t *testing.T) {
	configPath := GetConfigFilePath()
	defer os.Remove(configPath)

	apiPortA := getFreePort()
	engineA := NewEngine(Config{
		ServerPort: 0,
		ClientPort: 0,
		APIPort:    apiPortA,
		Hostname:   "PersistNodeA",
	})

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	require.NoError(t, engineA.Start(ctx))

	client := &http.Client{Timeout: 5 * time.Second}

	// 1. Set custom download_dir via POST /api/v1/config
	customDesktopDir := filepath.Join(os.TempDir(), "mops_user_desktop_dir")
	defer os.RemoveAll(customDesktopDir)

	postBody, _ := json.Marshal(map[string]string{
		"download_dir": customDesktopDir,
	})
	resp, err := client.Post(fmt.Sprintf("http://127.0.0.1:%d/api/v1/config", apiPortA), "application/json", bytes.NewBuffer(postBody))
	require.NoError(t, err)
	require.Equal(t, http.StatusOK, resp.StatusCode)
	resp.Body.Close()

	// Verify in-memory of EngineA
	assert.Equal(t, customDesktopDir, engineA.GetDownloadDir())

	// Verify raw config.json contains ONLY the modified download_dir and no other unmodified defaults
	rawBytes, err := os.ReadFile(configPath)
	require.NoError(t, err)
	var rawMap map[string]interface{}
	require.NoError(t, json.Unmarshal(rawBytes, &rawMap))
	assert.Equal(t, customDesktopDir, rawMap["download_dir"])
	assert.Nil(t, rawMap["hostname"], "unmodified hostname must not be written to disk")
	assert.Nil(t, rawMap["server_port"], "unmodified server_port must not be written to disk")

	// Verify GET /api/v1/status returns updated download_dir
	statusResp, err := client.Get(fmt.Sprintf("http://127.0.0.1:%d/api/v1/status", apiPortA))
	require.NoError(t, err)
	var sData struct {
		Code int        `json:"code"`
		Data StatusData `json:"data"`
	}
	require.NoError(t, json.NewDecoder(statusResp.Body).Decode(&sData))
	statusResp.Body.Close()
	assert.Equal(t, customDesktopDir, sData.Data.DownloadDir)

	// Stop Engine A
	engineA.Stop()

	// 2. Simulate restarting MOPS / Desktop (NewEngine with empty config)
	engineB := NewEngine(Config{
		ServerPort: 0,
		ClientPort: 0,
		APIPort:    getFreePort(),
		Hostname:   "PersistNodeB",
	})
	require.NoError(t, engineB.Start(ctx))
	defer engineB.Stop()

	// Assert Engine B automatically loads customDesktopDir from config.json!
	assert.Equal(t, customDesktopDir, engineB.GetDownloadDir())
}

