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
