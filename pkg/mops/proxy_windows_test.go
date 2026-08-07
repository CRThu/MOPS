//go:build windows

package mops

import (
	"os"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestSystemProxyToggle(t *testing.T) {
	// Save initial status including environment variables
	origInfo, _ := GetSystemProxyInfo()

	defer func() {
		// Restore original state after test
		_ = RestoreSystemProxyInfo(origInfo)
	}()

	// Test enable
	testProxy := "127.0.0.1:10081"
	err := SetSystemProxy(true, testProxy)
	require.NoError(t, err)

	enabled, server, err := GetSystemProxyStatus()
	require.NoError(t, err)
	assert.True(t, enabled)
	assert.Equal(t, testProxy, server)

	// Verify environment variables were set
	info, err := GetSystemProxyInfo()
	require.NoError(t, err)
	assert.True(t, info.Enabled)
	assert.Equal(t, "http://127.0.0.1:10081", os.Getenv("HTTP_PROXY"))
	assert.Equal(t, "http://127.0.0.1:10081", os.Getenv("HTTPS_PROXY"))
	assert.Equal(t, "socks5://127.0.0.1:10081", os.Getenv("ALL_PROXY"))
	assert.NotEmpty(t, os.Getenv("NO_PROXY"))

	// Test disable
	err = SetSystemProxy(false, "")
	require.NoError(t, err)

	enabled, _, err = GetSystemProxyStatus()
	require.NoError(t, err)
	assert.False(t, enabled)

	// Verify environment variables were cleared
	assert.Empty(t, os.Getenv("HTTP_PROXY"))
	assert.Empty(t, os.Getenv("HTTPS_PROXY"))
	assert.Empty(t, os.Getenv("ALL_PROXY"))
}

func TestSetSystemProxyInvalidAddrFallback(t *testing.T) {
	origInfo, _ := GetSystemProxyInfo()
	defer func() {
		_ = RestoreSystemProxyInfo(origInfo)
	}()

	// Test passing address without port
	err := SetSystemProxy(true, "127.0.0.1")
	assert.NoError(t, err)

	info, err := GetSystemProxyInfo()
	require.NoError(t, err)
	assert.True(t, info.Enabled)
	// Should fallback to default 127.0.0.1:10081
	assert.Equal(t, "127.0.0.1:10081", info.ProxyServer)
}
