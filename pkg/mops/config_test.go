package mops

import (
	"encoding/json"
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
	loaded := LoadPersistentConfig(Config{})
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

func TestSparseIncrementalConfigSave(t *testing.T) {
	configPath := GetConfigFilePath()
	defer os.Remove(configPath)

	// 1. Initial incremental update: only modify download_dir
	err := UpdatePersistentConfig(func(p *PersistentConfig) {
		p.DownloadDir = "C:/Users/SparseUser/Desktop"
	})
	require.NoError(t, err)

	// Read raw disk bytes and decode into generic map
	rawBytes, err := os.ReadFile(configPath)
	require.NoError(t, err)

	var rawMap map[string]interface{}
	require.NoError(t, json.Unmarshal(rawBytes, &rawMap))

	// Assert only download_dir is written to disk (sparse override)
	assert.Equal(t, "C:/Users/SparseUser/Desktop", rawMap["download_dir"])
	assert.Nil(t, rawMap["hostname"], "hostname must NOT be written when unmodified")
	assert.Nil(t, rawMap["server_port"], "server_port must NOT be written when unmodified")
	assert.Nil(t, rawMap["advertise"], "advertise must NOT be written when unmodified")
	assert.Len(t, rawMap, 1, "config.json should contain exactly 1 field")

	// 2. Second incremental update: modify advertise
	err = UpdatePersistentConfig(func(p *PersistentConfig) {
		p.Advertise = "192.168.1.188"
	})
	require.NoError(t, err)

	rawBytes, err = os.ReadFile(configPath)
	require.NoError(t, err)

	var rawMap2 map[string]interface{}
	require.NoError(t, json.Unmarshal(rawBytes, &rawMap2))

	assert.Equal(t, "C:/Users/SparseUser/Desktop", rawMap2["download_dir"])
	assert.Equal(t, "192.168.1.188", rawMap2["advertise"])
	assert.Nil(t, rawMap2["hostname"])
	assert.Len(t, rawMap2, 2, "config.json should contain exactly 2 fields")

	// 3. LoadPersistentConfig merges properly into dynamic defaults
	defaultBase := Config{
		Hostname:   "DynamicSystemHost",
		ListenAddr: "127.0.0.1",
	}
	merged := LoadPersistentConfig(defaultBase)
	assert.Equal(t, "C:/Users/SparseUser/Desktop", merged.DownloadDir)
	assert.Equal(t, "192.168.1.188", merged.Advertise)
	assert.Equal(t, "DynamicSystemHost", merged.Hostname, "dynamic hostname must be preserved")
	assert.Equal(t, "127.0.0.1", merged.ListenAddr)
}

func TestNewEngineWithPersistentConfig(t *testing.T) {
	configPath := GetConfigFilePath()
	defer os.Remove(configPath)

	customPath := "C:/Users/TestUser/Desktop"
	err := UpdatePersistentConfig(func(p *PersistentConfig) {
		p.DownloadDir = customPath
		p.Strategy = "hash"
	})
	require.NoError(t, err)

	// NewEngine with empty config should load customPath and hash strategy
	eng := NewEngine(Config{})
	assert.Equal(t, customPath, eng.GetDownloadDir())
	assert.Equal(t, "hash", eng.cfg.Strategy)

	// Explicit override should take precedence
	engOverride := NewEngine(Config{
		DownloadDir: "D:/ExplicitOverride",
	})
	assert.Equal(t, "D:/ExplicitOverride", engOverride.GetDownloadDir())
}

func TestConcurrentUpdatePersistentConfig(t *testing.T) {
	configPath := GetConfigFilePath()
	defer os.Remove(configPath)

	const goroutines = 10
	done := make(chan bool, goroutines)

	for i := 0; i < goroutines; i++ {
		go func(idx int) {
			_ = UpdatePersistentConfig(func(p *PersistentConfig) {
				p.Strategy = "hash"
			})
			done <- true
		}(i)
	}

	for i := 0; i < goroutines; i++ {
		<-done
	}

	loaded := LoadPersistentConfig(Config{})
	assert.Equal(t, "hash", loaded.Strategy)
}

func TestSavePersistentConfigFull(t *testing.T) {
	configPath := GetConfigFilePath()
	defer os.Remove(configPath)

	fullCfg := Config{
		ServerPort:  10090,
		ClientPort:  10091,
		APIPort:     10092,
		ListenAddr:  "0.0.0.0",
		Hostname:    "FullConfigHost",
		Advertise:   "10.0.0.1",
		Strategy:    "hash",
		DownloadDir: "D:/FullDownloads",
	}

	err := SavePersistentConfig(fullCfg)
	require.NoError(t, err)

	loaded := LoadPersistentConfig(Config{})
	assert.Equal(t, 10090, loaded.ServerPort)
	assert.Equal(t, 10091, loaded.ClientPort)
	assert.Equal(t, 10092, loaded.APIPort)
	assert.Equal(t, "0.0.0.0", loaded.ListenAddr)
	assert.Equal(t, "FullConfigHost", loaded.Hostname)
	assert.Equal(t, "10.0.0.1", loaded.Advertise)
	assert.Equal(t, "hash", loaded.Strategy)
	assert.Equal(t, "D:/FullDownloads", loaded.DownloadDir)
}



