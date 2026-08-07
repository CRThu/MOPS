package mops

import (
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

func TestServiceProgram(t *testing.T) {
	eng := NewEngine(Config{
		ServerPort: getFreePort(),
		ClientPort: getFreePort(),
		ListenAddr: "127.0.0.1",
		Hostname:   "TestSvc",
		Advertise:  "127.0.0.1",
	})
	disc := NewDiscovery(eng)

	prg := &program{
		engine: eng,
		disc:   disc,
	}

	err := prg.Start(nil)
	assert.NoError(t, err)

	time.Sleep(50 * time.Millisecond)

	err = prg.Stop(nil)
	assert.NoError(t, err)
}

func TestControlServiceInvalidAction(t *testing.T) {
	cfg := Config{
		ServerPort: 10080,
		ClientPort: 10081,
	}
	err := ControlService("invalid_action", cfg)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "unknown service command")
}

func TestCopyFileWithOverwrite(t *testing.T) {
	tempDir, err := os.MkdirTemp("", "mops_copy_test_*")
	assert.NoError(t, err)
	defer os.RemoveAll(tempDir)

	srcPath := filepath.Join(tempDir, "v2_mops.exe")
	dstPath := filepath.Join(tempDir, "target_mops.exe")

	// Create old file
	assert.NoError(t, os.WriteFile(dstPath, []byte("OLD_VERSION_V1"), 0755))

	// Create new binary file
	assert.NoError(t, os.WriteFile(srcPath, []byte("NEW_VERSION_V2_EXECUTABLE"), 0755))

	// Overwrite copy
	err = copyFileWithOverwrite(srcPath, dstPath)
	assert.NoError(t, err)

	content, err := os.ReadFile(dstPath)
	assert.NoError(t, err)
	assert.Equal(t, "NEW_VERSION_V2_EXECUTABLE", string(content))
}

func TestIsAdministrator(t *testing.T) {
	// Call IsAdministrator without crashing
	isAdmin := IsAdministrator()
	t.Logf("IsAdministrator returned: %v", isAdmin)
}

func TestCopyFileWithOverwriteErrors(t *testing.T) {
	tempDir, err := os.MkdirTemp("", "mops_copy_err_*")
	assert.NoError(t, err)
	defer os.RemoveAll(tempDir)

	nonExistentSrc := filepath.Join(tempDir, "non_existent.exe")
	dstPath := filepath.Join(tempDir, "target.exe")

	err = copyFileWithOverwrite(nonExistentSrc, dstPath)
	assert.Error(t, err)
}

func TestControlServiceLifecycle(t *testing.T) {
	if !IsAdministrator() {
		t.Skip("Skipping live Windows service test: administrative privileges required")
	}

	cfg := Config{
		ServerPort: 10890,
		ClientPort: 10891,
		APIPort:    10892,
		ListenAddr: "127.0.0.1",
		Hostname:   "TestServiceHost",
	}

	// 1. Clean up any leftover service registration
	_ = ControlService("uninstall", cfg)
	time.Sleep(200 * time.Millisecond)

	// 2. Test Install
	err := ControlService("install", cfg)
	assert.NoError(t, err, "service install should succeed")

	// Re-installing existing service should return nil (already installed message)
	err = ControlService("install", cfg)
	assert.NoError(t, err, "installing existing service should not fail")

	// 3. Test Start
	err = ControlService("start", cfg)
	assert.NoError(t, err, "service start should succeed")
	time.Sleep(1 * time.Second)

	// 4. Test Stop
	err = ControlService("stop", cfg)
	assert.NoError(t, err, "service stop should succeed")
	time.Sleep(300 * time.Millisecond)

	// 5. Test Update
	err = ControlService("update", cfg)
	assert.NoError(t, err, "service update should succeed")
	time.Sleep(500 * time.Millisecond)

	_ = ControlService("stop", cfg)
	time.Sleep(300 * time.Millisecond)

	// 6. Test Uninstall
	err = ControlService("uninstall", cfg)
	assert.NoError(t, err, "service uninstall should succeed")
}
