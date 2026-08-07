package mops

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync/atomic"
	"time"
)

// APIResponse defines standard JSON wrapper for REST API responses.
type APIResponse struct {
	Code    int         `json:"code"`
	Message string      `json:"message"`
	Data    interface{} `json:"data,omitempty"`
	Total   int         `json:"total,omitempty"`
}

// StatusData defines payload for /api/v1/status endpoint.
type StatusData struct {
	Hostname      string          `json:"hostname"`
	Strategy      string          `json:"strategy"`
	ClientPort    int             `json:"client_port"`
	ServerPort    int             `json:"server_port"`
	APIPort       int             `json:"api_port"`
	ClientEnabled bool            `json:"client_enabled"`
	ServerEnabled bool            `json:"server_enabled"`
	SystemProxy   SystemProxyInfo `json:"system_proxy"`
	SpeedUp       float64         `json:"speed_up"`
	SpeedDown     float64         `json:"speed_down"`
	BytesUp       uint64          `json:"bytes_up"`
	BytesDown     uint64          `json:"bytes_down"`
	TotalNodes    int             `json:"total_nodes"`
	OnlineNodes   int             `json:"online_nodes"`
}

// APIServer manages the RESTful HTTP API server.
type APIServer struct {
	engine   *Engine
	server   *http.Server
	listener net.Listener
}

// NewAPIServer creates a new RESTful API server instance.
func NewAPIServer(engine *Engine) *APIServer {
	return &APIServer{
		engine: engine,
	}
}

// Start launches the HTTP server listening on configured APIPort.
func (a *APIServer) Start(port int, listenAddr string) error {
	if port <= 0 {
		return fmt.Errorf("invalid API port: %d", port)
	}

	addr := fmt.Sprintf("0.0.0.0:%d", port)
	l, err := net.Listen("tcp", addr)
	if err != nil {
		return fmt.Errorf("failed to listen on API port %s: %w", addr, err)
	}
	a.listener = l

	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/nodes", a.handleGetNodes)
	mux.HandleFunc("/api/v1/status", a.handleGetStatus)
	mux.HandleFunc("/api/v1/files/transfer", a.handleFileTransfer)
	mux.HandleFunc("/api/v1/system-proxy", a.handleSystemProxy)
	mux.HandleFunc("/api/v1/client", a.handleClientControl)
	mux.HandleFunc("/api/v1/server", a.handleServerControl)

	a.server = &http.Server{
		Handler: mux,
	}

	go func() {
		_ = a.server.Serve(l)
	}()

	return nil
}

// Stop gracefully shuts down the API server.
func (a *APIServer) Stop() {
	if a.server != nil {
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		_ = a.server.Shutdown(ctx)
	}
}

func (a *APIServer) handleGetNodes(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, APIResponse{
			Code:    http.StatusMethodNotAllowed,
			Message: "Method Not Allowed",
		})
		return
	}

	nodes := a.engine.GetNodes()
	writeJSON(w, http.StatusOK, APIResponse{
		Code:    http.StatusOK,
		Message: "success",
		Data:    nodes,
		Total:   len(nodes),
	})
}

func (a *APIServer) handleGetStatus(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, APIResponse{
			Code:    http.StatusMethodNotAllowed,
			Message: "Method Not Allowed",
		})
		return
	}

	nodes := a.engine.GetNodes()
	onlineCount := 0
	for _, n := range nodes {
		if n.Status == "ONLINE" {
			onlineCount++
		}
	}

	speedUp, speedDown := a.engine.GetSpeed()

	sysProxyInfo, _ := GetSystemProxyInfo()

	status := StatusData{
		Hostname:      a.engine.cfg.Hostname,
		Strategy:      a.engine.cfg.Strategy,
		ClientPort:    a.engine.cfg.ClientPort,
		ServerPort:    a.engine.cfg.ServerPort,
		APIPort:       a.engine.cfg.APIPort,
		ClientEnabled: a.engine.GetClientEnabled(),
		ServerEnabled: a.engine.GetServerEnabled(),
		SystemProxy:   sysProxyInfo,
		SpeedUp:       speedUp,
		SpeedDown:     speedDown,
		BytesUp:       atomic.LoadUint64(&a.engine.bytesUp),
		BytesDown:     atomic.LoadUint64(&a.engine.bytesDown),
		TotalNodes:    len(nodes),
		OnlineNodes:   onlineCount,
	}

	writeJSON(w, http.StatusOK, APIResponse{
		Code:    http.StatusOK,
		Message: "success",
		Data:    status,
	})
}

func (a *APIServer) handleFileTransfer(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, APIResponse{
			Code:    http.StatusMethodNotAllowed,
			Message: "Method Not Allowed",
		})
		return
	}

	targetIP := r.URL.Query().Get("target_ip")
	if targetIP == "" {
		writeJSON(w, http.StatusBadRequest, APIResponse{
			Code:    http.StatusBadRequest,
			Message: "target_ip parameter is required",
		})
		return
	}

	targetPortStr := r.URL.Query().Get("target_port")
	targetPort := 10080
	if targetPortStr != "" {
		if p, err := strconv.Atoi(targetPortStr); err == nil && p > 0 {
			targetPort = p
		}
	}

	filePath := r.URL.Query().Get("path")
	var reader io.Reader
	var fileName string
	var fileSize int64
	var fileHash string

	if filePath != "" {
		file, err := os.Open(filePath)
		if err != nil {
			writeJSON(w, http.StatusBadRequest, APIResponse{
				Code:    http.StatusBadRequest,
				Message: fmt.Sprintf("failed to open file %s: %v", filePath, err),
			})
			return
		}
		defer file.Close()

		stat, err := file.Stat()
		if err != nil {
			writeJSON(w, http.StatusBadRequest, APIResponse{
				Code:    http.StatusBadRequest,
				Message: fmt.Sprintf("failed to stat file %s: %v", filePath, err),
			})
			return
		}

		fileName = stat.Name()
		fileSize = stat.Size()
		reader = file
	} else {
		fileName = r.URL.Query().Get("file_name")
		if fileName == "" {
			fileName = "transferred_file.bin"
		}
		fileSize = r.ContentLength
		reader = r.Body
	}

	computedHash, err := a.engine.SendFileToNode(targetIP, targetPort, fileName, reader, fileSize, fileHash)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, APIResponse{
			Code:    http.StatusInternalServerError,
			Message: fmt.Sprintf("Failed to transfer file to %s:%d: %v", targetIP, targetPort, err),
		})
		return
	}

	writeJSON(w, http.StatusOK, APIResponse{
		Code:    http.StatusOK,
		Message: "file transfer completed successfully",
		Data: map[string]interface{}{
			"target_ip":   targetIP,
			"target_port": targetPort,
			"file_name":   fileName,
			"file_size":   fileSize,
			"file_hash":   computedHash,
		},
	})
}

func (a *APIServer) handleSystemProxy(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		info, err := GetSystemProxyInfo()
		if err != nil {
			writeJSON(w, http.StatusInternalServerError, APIResponse{
				Code:    http.StatusInternalServerError,
				Message: fmt.Sprintf("failed to get system proxy info: %v", err),
			})
			return
		}
		writeJSON(w, http.StatusOK, APIResponse{
			Code:    http.StatusOK,
			Message: "success",
			Data:    info,
		})

	case http.MethodPost:
		var req struct {
			Action    string `json:"action"`
			Enable    *bool  `json:"enable"`
			ProxyAddr string `json:"proxy_addr"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeJSON(w, http.StatusBadRequest, APIResponse{
				Code:    http.StatusBadRequest,
				Message: "invalid JSON body",
			})
			return
		}

		enableProxy := false
		actionLower := strings.ToLower(req.Action)
		if actionLower == "off" || actionLower == "clear" {
			enableProxy = false
		} else if actionLower == "on" || actionLower == "set" {
			enableProxy = true
		} else if req.Enable != nil {
			enableProxy = *req.Enable
		}

		if enableProxy && req.ProxyAddr == "" {
			req.ProxyAddr = fmt.Sprintf("127.0.0.1:%d", a.engine.cfg.ClientPort)
		}

		if err := SetSystemProxy(enableProxy, req.ProxyAddr); err != nil {
			writeJSON(w, http.StatusInternalServerError, APIResponse{
				Code:    http.StatusInternalServerError,
				Message: fmt.Sprintf("failed to set system proxy: %v", err),
			})
			return
		}

		info, _ := GetSystemProxyInfo()
		writeJSON(w, http.StatusOK, APIResponse{
			Code:    http.StatusOK,
			Message: "system proxy updated successfully",
			Data:    info,
		})

	default:
		writeJSON(w, http.StatusMethodNotAllowed, APIResponse{
			Code:    http.StatusMethodNotAllowed,
			Message: "Method Not Allowed",
		})
	}
}

func (a *APIServer) handleClientControl(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		writeJSON(w, http.StatusOK, APIResponse{
			Code:    http.StatusOK,
			Message: "success",
			Data: map[string]interface{}{
				"enabled": a.engine.GetClientEnabled(),
				"port":    a.engine.cfg.ClientPort,
			},
		})

	case http.MethodPost:
		var req struct {
			Enable bool `json:"enable"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeJSON(w, http.StatusBadRequest, APIResponse{
				Code:    http.StatusBadRequest,
				Message: "invalid JSON body",
			})
			return
		}

		if err := a.engine.SetClientEnabled(req.Enable); err != nil {
			writeJSON(w, http.StatusInternalServerError, APIResponse{
				Code:    http.StatusInternalServerError,
				Message: fmt.Sprintf("failed to change client state: %v", err),
			})
			return
		}

		writeJSON(w, http.StatusOK, APIResponse{
			Code:    http.StatusOK,
			Message: "client state updated successfully",
			Data: map[string]interface{}{
				"enabled": a.engine.GetClientEnabled(),
				"port":    a.engine.cfg.ClientPort,
			},
		})

	default:
		writeJSON(w, http.StatusMethodNotAllowed, APIResponse{
			Code:    http.StatusMethodNotAllowed,
			Message: "Method Not Allowed",
		})
	}
}

func (a *APIServer) handleServerControl(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		writeJSON(w, http.StatusOK, APIResponse{
			Code:    http.StatusOK,
			Message: "success",
			Data: map[string]interface{}{
				"enabled": a.engine.GetServerEnabled(),
				"port":    a.engine.cfg.ServerPort,
			},
		})

	case http.MethodPost:
		var req struct {
			Enable bool `json:"enable"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeJSON(w, http.StatusBadRequest, APIResponse{
				Code:    http.StatusBadRequest,
				Message: "invalid JSON body",
			})
			return
		}

		if err := a.engine.SetServerEnabled(req.Enable); err != nil {
			writeJSON(w, http.StatusInternalServerError, APIResponse{
				Code:    http.StatusInternalServerError,
				Message: fmt.Sprintf("failed to change server state: %v", err),
			})
			return
		}

		writeJSON(w, http.StatusOK, APIResponse{
			Code:    http.StatusOK,
			Message: "server state updated successfully",
			Data: map[string]interface{}{
				"enabled": a.engine.GetServerEnabled(),
				"port":    a.engine.cfg.ServerPort,
			},
		})

	default:
		writeJSON(w, http.StatusMethodNotAllowed, APIResponse{
			Code:    http.StatusMethodNotAllowed,
			Message: "Method Not Allowed",
		})
	}
}

func writeJSON(w http.ResponseWriter, statusCode int, data interface{}) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(statusCode)
	_ = json.NewEncoder(w).Encode(data)
}
