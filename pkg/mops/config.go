package mops

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sync"
)

var configMu sync.RWMutex

// PersistentConfig represents sparse user-defined overrides on disk.
// Fields that are not explicitly overridden by the user are omitted,
// preserving the application's ability to dynamically adapt to system defaults.
type PersistentConfig struct {
	ServerPort  int    `json:"server_port,omitempty"`
	ClientPort  int    `json:"client_port,omitempty"`
	APIPort     int    `json:"api_port,omitempty"`
	ListenAddr  string `json:"listen_addr,omitempty"`
	Hostname    string `json:"hostname,omitempty"`
	Advertise   string `json:"advertise,omitempty"`
	Strategy    string `json:"strategy,omitempty"`
	DownloadDir string `json:"download_dir,omitempty"`
}

// GetConfigFilePath returns the path to config.json located in the same directory as the executable.
func GetConfigFilePath() string {
	exePath, err := os.Executable()
	if err == nil && exePath != "" {
		dir := filepath.Dir(exePath)
		return filepath.Join(dir, "config.json")
	}
	return "./config.json"
}

// LoadPersistentConfig loads sparse overrides from config.json and merges them into defaultCfg.
func LoadPersistentConfig(defaultCfg Config) Config {
	configMu.RLock()
	defer configMu.RUnlock()

	path := GetConfigFilePath()
	data, err := os.ReadFile(path)
	if err != nil {
		return defaultCfg
	}

	var p PersistentConfig
	if err := json.Unmarshal(data, &p); err != nil {
		return defaultCfg
	}

	if p.ServerPort > 0 {
		defaultCfg.ServerPort = p.ServerPort
	}
	if p.ClientPort > 0 {
		defaultCfg.ClientPort = p.ClientPort
	}
	if p.APIPort > 0 {
		defaultCfg.APIPort = p.APIPort
	}
	if p.ListenAddr != "" {
		defaultCfg.ListenAddr = p.ListenAddr
	}
	if p.Hostname != "" {
		defaultCfg.Hostname = p.Hostname
	}
	if p.Advertise != "" {
		defaultCfg.Advertise = p.Advertise
	}
	if p.Strategy != "" {
		defaultCfg.Strategy = p.Strategy
	}
	if p.DownloadDir != "" {
		defaultCfg.DownloadDir = p.DownloadDir
	}
	return defaultCfg
}

// UpdatePersistentConfig performs an atomic incremental modification of config.json.
func UpdatePersistentConfig(modifier func(p *PersistentConfig)) error {
	configMu.Lock()
	defer configMu.Unlock()

	path := GetConfigFilePath()
	var p PersistentConfig
	if data, err := os.ReadFile(path); err == nil {
		_ = json.Unmarshal(data, &p)
	}

	modifier(&p)

	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return err
	}

	data, err := json.MarshalIndent(p, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0644)
}

// SavePersistentConfig saves configuration JSON into config.json.
func SavePersistentConfig(cfg Config) error {
	return UpdatePersistentConfig(func(p *PersistentConfig) {
		if cfg.ServerPort > 0 {
			p.ServerPort = cfg.ServerPort
		}
		if cfg.ClientPort > 0 {
			p.ClientPort = cfg.ClientPort
		}
		if cfg.APIPort > 0 {
			p.APIPort = cfg.APIPort
		}
		if cfg.ListenAddr != "" {
			p.ListenAddr = cfg.ListenAddr
		}
		if cfg.Hostname != "" {
			p.Hostname = cfg.Hostname
		}
		if cfg.Advertise != "" {
			p.Advertise = cfg.Advertise
		}
		if cfg.Strategy != "" {
			p.Strategy = cfg.Strategy
		}
		if cfg.DownloadDir != "" {
			p.DownloadDir = cfg.DownloadDir
		}
	})
}
