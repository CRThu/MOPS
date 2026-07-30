//go:build windows

package mops

import (
	"fmt"
	"syscall"

	"golang.org/x/sys/windows/registry"
)

const registryPath = `Software\Microsoft\Windows\CurrentVersion\Internet Settings`

var (
	modwininet            = syscall.NewLazyDLL("wininet.dll")
	procInternetSetOption = modwininet.NewProc("InternetSetOptionW")
)

const (
	INTERNET_OPTION_SETTINGS_CHANGED = 39
	INTERNET_OPTION_REFRESH          = 37
)

// SetSystemProxy enables or disables Windows system proxy via HKCU registry.
func SetSystemProxy(enable bool, proxyAddr string) error {
	key, err := registry.OpenKey(registry.CURRENT_USER, registryPath, registry.SET_VALUE|registry.QUERY_VALUE)
	if err != nil {
		return fmt.Errorf("failed to open registry key: %w", err)
	}
	defer key.Close()

	if enable {
		if proxyAddr == "" {
			proxyAddr = "127.0.0.1:10081"
		}
		if err := key.SetDWordValue("ProxyEnable", 1); err != nil {
			return fmt.Errorf("failed to set ProxyEnable=1: %w", err)
		}
		if err := key.SetStringValue("ProxyServer", proxyAddr); err != nil {
			return fmt.Errorf("failed to set ProxyServer: %w", err)
		}
	} else {
		if err := key.SetDWordValue("ProxyEnable", 0); err != nil {
			return fmt.Errorf("failed to set ProxyEnable=0: %w", err)
		}
	}

	notifySystemProxyChange()
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

func notifySystemProxyChange() {
	procInternetSetOption.Call(0, INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)
	procInternetSetOption.Call(0, INTERNET_OPTION_REFRESH, 0, 0)
}
