package mops

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestFormatBytes(t *testing.T) {
	assert.Equal(t, "0 B", FormatBytes(0))
	assert.Equal(t, "500 B", FormatBytes(500))
	assert.Equal(t, "1023 B", FormatBytes(1023))
	assert.Equal(t, "1.5 KB", FormatBytes(1536))
	assert.Equal(t, "10.0 MB", FormatBytes(10*1024*1024))
	assert.Equal(t, "2.5 GB", FormatBytes(uint64(2.5*1024*1024*1024)))
}

func TestFormatSpeed(t *testing.T) {
	assert.Equal(t, "0.0 B/s", FormatSpeed(0))
	assert.Equal(t, "500.0 B/s", FormatSpeed(500))
	assert.Equal(t, "12.5 KB/s", FormatSpeed(12.5*1024))
	assert.Equal(t, "1.50 MB/s", FormatSpeed(1.5*1024*1024))
	assert.Equal(t, "3.20 GB/s", FormatSpeed(3.2*1024*1024*1024))
}

func TestRenderStatus(t *testing.T) {
	nodes := []*Node{
		{
			ID:         "node-01",
			Hostname:   "Carrot-PC-72",
			IP:         "192.168.132.72",
			Port:       10080,
			Role:       "Server",
			Status:     "ONLINE",
			ActiveConn: 3,
			BytesUp:    12400000,
			BytesDown:  105800000,
		},
		{
			ID:         "node-02",
			Hostname:   "Carrot-PC-74",
			IP:         "192.168.132.74",
			Port:       10080,
			Role:       "Both",
			Status:     "ONLINE",
			ActiveConn: 2,
			BytesUp:    8100000,
			BytesDown:  84200000,
			IsMe:       true,
		},
	}

	out := RenderStatus(nodes, "round-robin", 10081, 12.5*1024, 780.5*1024)
	assert.Contains(t, out, "# MOPS Multi-node Proxy Cluster Status (Windows)")
	assert.Contains(t, out, "node-01")
	assert.Contains(t, out, "node-02 (me)")
	assert.Contains(t, out, "780.5 KB/s")
}

func TestRenderStatusWithProxyInfo(t *testing.T) {
	proxyInfo := SystemProxyInfo{
		Enabled:     true,
		ProxyServer: "127.0.0.1:7890",
		HttpProxy:   "http://127.0.0.1:7890",
	}

	out := RenderStatusWithProxyInfo(nil, "random", 10081, 0, 0, proxyInfo)
	assert.Contains(t, out, "System Proxy: ON (127.0.0.1:7890)")
	assert.Contains(t, out, "HTTP_PROXY: http://127.0.0.1:7890")
}
