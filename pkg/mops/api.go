package mops

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
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
	Hostname    string  `json:"hostname"`
	Strategy    string  `json:"strategy"`
	ClientPort  int     `json:"client_port"`
	ServerPort  int     `json:"server_port"`
	APIPort     int     `json:"api_port"`
	SpeedUp     float64 `json:"speed_up"`
	SpeedDown   float64 `json:"speed_down"`
	BytesUp     uint64  `json:"bytes_up"`
	BytesDown   uint64  `json:"bytes_down"`
	TotalNodes  int     `json:"total_nodes"`
	OnlineNodes int     `json:"online_nodes"`
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

	a.server = &http.Server{
		Handler:      mux,
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 10 * time.Second,
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

	status := StatusData{
		Hostname:    a.engine.cfg.Hostname,
		Strategy:    a.engine.cfg.Strategy,
		ClientPort:  a.engine.cfg.ClientPort,
		ServerPort:  a.engine.cfg.ServerPort,
		APIPort:     a.engine.cfg.APIPort,
		SpeedUp:     speedUp,
		SpeedDown:   speedDown,
		BytesUp:     atomic.LoadUint64(&a.engine.bytesUp),
		BytesDown:   atomic.LoadUint64(&a.engine.bytesDown),
		TotalNodes:  len(nodes),
		OnlineNodes: onlineCount,
	}

	writeJSON(w, http.StatusOK, APIResponse{
		Code:    http.StatusOK,
		Message: "success",
		Data:    status,
	})
}

func writeJSON(w http.ResponseWriter, statusCode int, data interface{}) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(statusCode)
	_ = json.NewEncoder(w).Encode(data)
}
