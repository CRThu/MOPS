package mops

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestPersistentConfigSaveAndLoad(t *testing.T) {
	configPath := GetConfigFilePath()
	defer os.Remove(configPath)

	defaultCfg := Config{
		ServerPort:  10080,
		ClientPort:  10081,
		APIPort:     10082,
		DownloadDir: "./downloads",
	}

	// 1. Save new config
	toSave := defaultCfg
	toSave.DownloadDir = "D:/CustomTestDownloads"
	err := SavePersistentConfig(toSave)
	require.NoError(t, err)

	// 2. Load and verify
	loaded := LoadPersistentConfig(defaultCfg)
	assert.Equal(t, "D:/CustomTestDownloads", loaded.DownloadDir)
	assert.Equal(t, 10080, loaded.ServerPort)

	// 3. Test corrupted JSON fallback
	require.NoError(t, os.WriteFile(configPath, []byte("{invalid_json_content}"), 0644))
	fallbackCfg := LoadPersistentConfig(defaultCfg)
	assert.Equal(t, "./downloads", fallbackCfg.DownloadDir)
}

func TestGetConfigFilePath(t *testing.T) {
	path := GetConfigFilePath()
	assert.NotEmpty(t, path)
	assert.Equal(t, "config.json", filepath.Base(path))
}
