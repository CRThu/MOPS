//go:build windows

package mops

import (
	"fmt"
	"net"
	"os"
	"strconv"
	"strings"
	"syscall"
	"unsafe"

	"golang.org/x/sys/windows/registry"
)

const registryPath = `Software\Microsoft\Windows\CurrentVersion\Internet Settings`
const envRegistryPath = `Environment`

var (
	modwininet             = syscall.NewLazyDLL("wininet.dll")
	procInternetSetOption  = modwininet.NewProc("InternetSetOptionW")
	moduser32              = syscall.NewLazyDLL("user32.dll")
	procSendMessageTimeout = moduser32.NewProc("SendMessageTimeoutW")
)

const (
	INTERNET_OPTION_SETTINGS_CHANGED = 39
	INTERNET_OPTION_REFRESH          = 37

	HWND_BROADCAST   = 0xffff
	WM_SETTINGCHANGE = 0x001A
	SMTO_ABORTIFHUNG = 0x0002
)

var proxyEnvKeys = []string{
	"HTTP_PROXY",
	"HTTPS_PROXY",
	"NO_PROXY",
}

// SetSystemProxy enables or disables Windows system proxy via HKCU registry and environment variables.
func SetSystemProxy(enable bool, proxyAddr string) error {
	key, err := registry.OpenKey(registry.CURRENT_USER, registryPath, registry.SET_VALUE|registry.QUERY_VALUE)
	if err != nil {
		return fmt.Errorf("failed to open registry key: %w", err)
	}
	defer key.Close()

	envKey, err := registry.OpenKey(registry.CURRENT_USER, envRegistryPath, registry.SET_VALUE|registry.QUERY_VALUE)
	if err != nil {
		return fmt.Errorf("failed to open environment registry key: %w", err)
	}
	defer envKey.Close()

	if enable {
		cleanAddr := CleanProxyAddr(proxyAddr)
		if err := key.SetDWordValue("ProxyEnable", 1); err != nil {
			return fmt.Errorf("failed to set ProxyEnable=1: %w", err)
		}
		if err := key.SetStringValue("ProxyServer", cleanAddr); err != nil {
			return fmt.Errorf("failed to set ProxyServer: %w", err)
		}
		_ = key.SetStringValue("ProxyOverride", "<local>;localhost;127.*;192.168.*;10.*")

		// 1. Set uppercase environment variables in HKCU\Environment
		httpVal := fmt.Sprintf("http://%s", cleanAddr)
		noProxyVal := "localhost,127.0.0.1,::1,192.168.0.0/16,10.0.0.0/8,<local>"

		envMap := map[string]string{
			"HTTP_PROXY":  httpVal,
			"HTTPS_PROXY": httpVal,
			"NO_PROXY":    noProxyVal,
		}

		for k, v := range envMap {
			_ = envKey.SetStringValue(k, v)
			_ = os.Setenv(k, v)
		}
	} else {
		if err := key.SetDWordValue("ProxyEnable", 0); err != nil {
			return fmt.Errorf("failed to set ProxyEnable=0: %w", err)
		}

		// 2. Delete all proxy environment variables from HKCU\Environment and current process
		for _, k := range proxyEnvKeys {
			_ = envKey.DeleteValue(k)
			_ = os.Unsetenv(k)
		}
	}

	notifySystemProxyChange()
	notifyEnvironmentChange()
	return nil
}

// GetSystemProxyStatus reads current system proxy state from Windows registry.
func GetSystemProxyStatus() (bool, string, error) {
	key, err := registry.OpenKey(registry.CURRENT_USER, registryPath, registry.QUERY_VALUE)
	if err != nil {
		return false, "", fmt.Errorf("failed to open registry key: %w", err)
	}
	defer key.Close()

	enableVal, _, err := key.GetIntegerValue("ProxyEnable")
	if err != nil {
		enableVal = 0
	}

	serverVal, _, err := key.GetStringValue("ProxyServer")
	if err != nil {
		serverVal = ""
	}

	return enableVal == 1, serverVal, nil
}

// SystemProxyInfo defines full proxy state including environment variables.
type SystemProxyInfo struct {
	Enabled     bool   `json:"enabled"`
	ProxyServer string `json:"proxy_server"`
	HttpProxy   string `json:"http_proxy"`
	HttpsProxy  string `json:"https_proxy"`
	NoProxy     string `json:"no_proxy"`
}

// GetSystemProxyInfo reads system proxy and uppercase environment variables.
func GetSystemProxyInfo() (SystemProxyInfo, error) {
	enabled, server, err := GetSystemProxyStatus()
	info := SystemProxyInfo{
		Enabled:     enabled,
		ProxyServer: server,
		HttpProxy:   os.Getenv("HTTP_PROXY"),
		HttpsProxy:  os.Getenv("HTTPS_PROXY"),
		NoProxy:     os.Getenv("NO_PROXY"),
	}

	envKey, envErr := registry.OpenKey(registry.CURRENT_USER, envRegistryPath, registry.QUERY_VALUE)
	if envErr == nil {
		defer envKey.Close()
		if info.HttpProxy == "" {
			info.HttpProxy, _, _ = envKey.GetStringValue("HTTP_PROXY")
		}
		if info.HttpsProxy == "" {
			info.HttpsProxy, _, _ = envKey.GetStringValue("HTTPS_PROXY")
		}
		if info.NoProxy == "" {
			info.NoProxy, _, _ = envKey.GetStringValue("NO_PROXY")
		}
	}

	return info, err
}

func notifySystemProxyChange() {
	procInternetSetOption.Call(0, INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)
	procInternetSetOption.Call(0, INTERNET_OPTION_REFRESH, 0, 0)
}

func notifyEnvironmentChange() {
	envStr, _ := syscall.UTF16PtrFromString("Environment")
	var result uintptr
	procSendMessageTimeout.Call(
		uintptr(HWND_BROADCAST),
		uintptr(WM_SETTINGCHANGE),
		0,
		uintptr(unsafe.Pointer(envStr)),
		uintptr(SMTO_ABORTIFHUNG),
		5000,
		uintptr(unsafe.Pointer(&result)),
	)
}

// RestoreSystemProxyInfo restores full system proxy registry and environment state.
func RestoreSystemProxyInfo(info SystemProxyInfo) error {
	if info.Enabled {
		if err := SetSystemProxy(true, info.ProxyServer); err != nil {
			return err
		}
	} else {
		if err := SetSystemProxy(false, ""); err != nil {
			return err
		}
	}

	envKey, err := registry.OpenKey(registry.CURRENT_USER, envRegistryPath, registry.SET_VALUE)
	if err == nil {
		defer envKey.Close()
		if info.HttpProxy != "" {
			_ = envKey.SetStringValue("HTTP_PROXY", info.HttpProxy)
			_ = os.Setenv("HTTP_PROXY", info.HttpProxy)
		}
		if info.HttpsProxy != "" {
			_ = envKey.SetStringValue("HTTPS_PROXY", info.HttpsProxy)
			_ = os.Setenv("HTTPS_PROXY", info.HttpsProxy)
		}

		if info.NoProxy != "" {
			_ = envKey.SetStringValue("NO_PROXY", info.NoProxy)
			_ = os.Setenv("NO_PROXY", info.NoProxy)
		}
	}
	notifyEnvironmentChange()
	return nil
}

// CleanProxyAddr normalizes user proxy input (e.g. "7897", "127.0.0.1:7897", "http://127.0.0.1:7897/", "127.0.0.1").
func CleanProxyAddr(proxyAddr string) string {
	proxyAddr = strings.TrimSpace(proxyAddr)
	if proxyAddr == "" {
		return "127.0.0.1:10081"
	}
	if idx := strings.Index(proxyAddr, "://"); idx != -1 {
		proxyAddr = proxyAddr[idx+3:]
	}
	proxyAddr = strings.TrimSuffix(proxyAddr, "/")

	if _, err := strconv.Atoi(proxyAddr); err == nil {
		return fmt.Sprintf("127.0.0.1:%s", proxyAddr)
	}

	if net.ParseIP(proxyAddr) != nil {
		return fmt.Sprintf("%s:10081", proxyAddr)
	}

	host, portStr, err := net.SplitHostPort(proxyAddr)
	if err != nil {
		if !strings.Contains(proxyAddr, ":") {
			return fmt.Sprintf("127.0.0.1:%s", proxyAddr)
		}
		return "127.0.0.1:10081"
	}

	if host == "" || host == "0.0.0.0" {
		host = "127.0.0.1"
	}
	return fmt.Sprintf("%s:%s", host, portStr)
}
