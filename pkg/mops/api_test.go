package mops

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"testing"
	"time"

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
