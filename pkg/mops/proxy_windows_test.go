//go:build windows

package mops

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestSystemProxyToggle(t *testing.T) {
	// Save initial status
	origEnabled, origServer, _ := GetSystemProxyStatus()

	defer func() {
		// Restore original state after test
		_ = SetSystemProxy(origEnabled, origServer)
	}()

	// Test enable
	testProxy := "127.0.0.1:10081"
	err := SetSystemProxy(true, testProxy)
	require.NoError(t, err)

	enabled, server, err := GetSystemProxyStatus()
	require.NoError(t, err)
	assert.True(t, enabled)
	assert.Equal(t, testProxy, server)

	// Test disable
	err = SetSystemProxy(false, "")
	require.NoError(t, err)

	enabled, _, err = GetSystemProxyStatus()
	require.NoError(t, err)
	assert.False(t, enabled)
}
