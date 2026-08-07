package mops

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sync"
)

var configMu sync.RWMutex

// GetConfigFilePath returns the path to config.json located in the same directory as the executable.
func GetConfigFilePath() string {
	exePath, err := os.Executable()
	if err == nil && exePath != "" {
		dir := filepath.Dir(exePath)
		return filepath.Join(dir, "config.json")
	}
	return "./config.json"
}

// LoadPersistentConfig loads persistent configuration from the exe directory config.json.
// Missing or default fields will preserve original default values.
func LoadPersistentConfig(defaultCfg Config) Config {
	configMu.RLock()
	defer configMu.RUnlock()

	path := GetConfigFilePath()
	data, err := os.ReadFile(path)
	if err != nil {
		return defaultCfg
	}

	var fileCfg Config
	if err := json.Unmarshal(data, &fileCfg); err != nil {
		return defaultCfg
	}

	if fileCfg.ServerPort > 0 {
		defaultCfg.ServerPort = fileCfg.ServerPort
	}
	if fileCfg.ClientPort > 0 {
		defaultCfg.ClientPort = fileCfg.ClientPort
	}
	if fileCfg.APIPort > 0 {
		defaultCfg.APIPort = fileCfg.APIPort
	}
	if fileCfg.ListenAddr != "" {
		defaultCfg.ListenAddr = fileCfg.ListenAddr
	}
	if fileCfg.Hostname != "" {
		defaultCfg.Hostname = fileCfg.Hostname
	}
	if fileCfg.Advertise != "" {
		defaultCfg.Advertise = fileCfg.Advertise
	}
	if fileCfg.Strategy != "" {
		defaultCfg.Strategy = fileCfg.Strategy
	}
	if fileCfg.DownloadDir != "" {
		defaultCfg.DownloadDir = fileCfg.DownloadDir
	}
	return defaultCfg
}

// SavePersistentConfig saves configuration JSON into config.json alongside executable.
func SavePersistentConfig(cfg Config) error {
	configMu.Lock()
	defer configMu.Unlock()

	path := GetConfigFilePath()
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return err
	}

	data, err := json.MarshalIndent(cfg, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0644)
}
