package mops

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	"github.com/kardianos/service"
	"github.com/spf13/cobra"
)

func fetchStatusFromAPI(apiPort int) (*StatusData, []*Node, error) {
	client := &http.Client{Timeout: 1 * time.Second}

	statusResp, err := client.Get(fmt.Sprintf("http://127.0.0.1:%d/api/v1/status", apiPort))
	if err != nil {
		return nil, nil, err
	}
	defer statusResp.Body.Close()
	if statusResp.StatusCode != http.StatusOK {
		return nil, nil, fmt.Errorf("unexpected status code: %d", statusResp.StatusCode)
	}

	var statusWrapper struct {
		Code    int        `json:"code"`
		Message string     `json:"message"`
		Data    StatusData `json:"data"`
	}
	if err := json.NewDecoder(statusResp.Body).Decode(&statusWrapper); err != nil {
		return nil, nil, err
	}

	nodesResp, err := client.Get(fmt.Sprintf("http://127.0.0.1:%d/api/v1/nodes", apiPort))
	if err != nil {
		return nil, nil, err
	}
	defer nodesResp.Body.Close()
	if nodesResp.StatusCode != http.StatusOK {
		return nil, nil, fmt.Errorf("unexpected status code: %d", nodesResp.StatusCode)
	}

	var nodesWrapper struct {
		Code    int     `json:"code"`
		Message string  `json:"message"`
		Data    []*Node `json:"data"`
	}
	if err := json.NewDecoder(nodesResp.Body).Decode(&nodesWrapper); err != nil {
		return nil, nil, err
	}

	return &statusWrapper.Data, nodesWrapper.Data, nil
}

func controlSystemProxyViaAPI(apiPort int, action string, customAddr string) error {
	client := &http.Client{Timeout: 2 * time.Second}
	urlStr := fmt.Sprintf("http://127.0.0.1:%d/api/v1/system-proxy", apiPort)

	switch action {
	case "on", "off", "set", "clear":
		reqBody := map[string]interface{}{
			"action":     action,
			"proxy_addr": customAddr,
		}
		b, _ := json.Marshal(reqBody)
		resp, err := client.Post(urlStr, "application/json", bytes.NewReader(b))
		if err != nil {
			return err
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			return fmt.Errorf("unexpected API status code: %d", resp.StatusCode)
		}
		if action == "on" || action == "set" {
			if customAddr == "" {
				fmt.Println("Windows System Proxy enabled & environment variables set via API.")
			} else {
				fmt.Printf("Windows System Proxy enabled & environment variables set via API -> %s\n", customAddr)
			}
		} else {
			fmt.Println("Windows System Proxy disabled & environment variables cleared via API.")
		}
		return nil

	case "status":
		resp, err := client.Get(urlStr)
		if err != nil {
			return err
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			return fmt.Errorf("unexpected API status code: %d", resp.StatusCode)
		}
		var wrapper struct {
			Code int             `json:"code"`
			Data SystemProxyInfo `json:"data"`
		}
		if err := json.NewDecoder(resp.Body).Decode(&wrapper); err != nil {
			return err
		}
		if wrapper.Data.Enabled {
			fmt.Printf("System Proxy is ON (API) -> %s\n", wrapper.Data.ProxyServer)
		} else {
			fmt.Println("System Proxy is OFF (API)")
		}
		fmt.Printf("HTTP_PROXY:  %s\n", wrapper.Data.HttpProxy)
		fmt.Printf("HTTPS_PROXY: %s\n", wrapper.Data.HttpsProxy)
		fmt.Printf("NO_PROXY:    %s\n", wrapper.Data.NoProxy)
		return nil
	}
	return fmt.Errorf("invalid action: %s", action)
}

func controlClientViaAPI(apiPort int, action string) error {
	client := &http.Client{Timeout: 2 * time.Second}
	urlStr := fmt.Sprintf("http://127.0.0.1:%d/api/v1/client", apiPort)

	switch action {
	case "on", "off":
		reqBody := map[string]interface{}{
			"enable": action == "on",
		}
		b, _ := json.Marshal(reqBody)
		resp, err := client.Post(urlStr, "application/json", bytes.NewReader(b))
		if err != nil {
			return err
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			return fmt.Errorf("unexpected API status code: %d", resp.StatusCode)
		}
		if action == "on" {
			fmt.Println("Client SOCKS5 Proxy listener started via API.")
		} else {
			fmt.Println("Client SOCKS5 Proxy listener stopped via API.")
		}
		return nil

	case "status":
		resp, err := client.Get(urlStr)
		if err != nil {
			return err
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			return fmt.Errorf("unexpected API status code: %d", resp.StatusCode)
		}
		var wrapper struct {
			Code int `json:"code"`
			Data struct {
				Enabled bool `json:"enabled"`
				Port    int  `json:"port"`
			} `json:"data"`
		}
		if err := json.NewDecoder(resp.Body).Decode(&wrapper); err != nil {
			return err
		}
		if wrapper.Data.Enabled {
			fmt.Printf("Client SOCKS5 Proxy is ON -> port :%d\n", wrapper.Data.Port)
		} else {
			fmt.Println("Client SOCKS5 Proxy is OFF")
		}
		return nil
	}
	return fmt.Errorf("invalid action: %s", action)
}

func controlServerViaAPI(apiPort int, action string) error {
	client := &http.Client{Timeout: 2 * time.Second}
	urlStr := fmt.Sprintf("http://127.0.0.1:%d/api/v1/server", apiPort)

	switch action {
	case "on", "off":
		reqBody := map[string]interface{}{
			"enable": action == "on",
		}
		b, _ := json.Marshal(reqBody)
		resp, err := client.Post(urlStr, "application/json", bytes.NewReader(b))
		if err != nil {
			return err
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			return fmt.Errorf("unexpected API status code: %d", resp.StatusCode)
		}
		if action == "on" {
			fmt.Println("Server TCP Proxy listener started via API.")
		} else {
			fmt.Println("Server TCP Proxy listener stopped via API.")
		}
		return nil

	case "status":
		resp, err := client.Get(urlStr)
		if err != nil {
			return err
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			return fmt.Errorf("unexpected API status code: %d", resp.StatusCode)
		}
		var wrapper struct {
			Code int `json:"code"`
			Data struct {
				Enabled bool `json:"enabled"`
				Port    int  `json:"port"`
			} `json:"data"`
		}
		if err := json.NewDecoder(resp.Body).Decode(&wrapper); err != nil {
			return err
		}
		if wrapper.Data.Enabled {
			fmt.Printf("Server TCP Proxy is ON -> port :%d\n", wrapper.Data.Port)
		} else {
			fmt.Println("Server TCP Proxy is OFF")
		}
		return nil
	}
	return fmt.Errorf("invalid action: %s", action)
}

func controlServiceViaAPI(apiPort int, action string, cfg Config) error {
	client := &http.Client{Timeout: 2 * time.Second}
	urlStr := fmt.Sprintf("http://127.0.0.1:%d/api/v1/service", apiPort)

	reqBody := map[string]interface{}{
		"action": action,
	}
	b, _ := json.Marshal(reqBody)
	resp, err := client.Post(urlStr, "application/json", bytes.NewReader(b))
	if err == nil {
		defer resp.Body.Close()
		if resp.StatusCode == http.StatusOK {
			fmt.Printf("Windows Service operation '%s' executed via API.\n", action)
			return nil
		}
	}
	return ControlService(action, cfg)
}

// Execute builds and executes the CLI commands.
func Execute() error {
	var (
		serverPort  int
		clientPort  int
		apiPort     int
		listenAddr  string
		advertise   string
		strategy    string
		downloadDir string
		nodes       []string
		watch       bool
	)

	defaultHostname, _ := os.Hostname()
	if defaultHostname == "" {
		defaultHostname = "Windows-PC"
	}
	var hostname string

	rootCmd := &cobra.Command{
		Use:     "mops",
		Short:   "MOPS Multi-node Outbound Proxy System",
		Version: "1.6.0",
		RunE: func(cmd *cobra.Command, args []string) error {
			cfg := Config{
				ServerPort:  serverPort,
				ClientPort:  clientPort,
				APIPort:     apiPort,
				ListenAddr:  listenAddr,
				Hostname:    hostname,
				Advertise:   advertise,
				Strategy:    strategy,
				DownloadDir: downloadDir,
			}
			if !service.Interactive() {
				return ControlService("run", cfg)
			}
			return runDaemon(cfg, nodes)
		},
	}

	rootCmd.PersistentFlags().StringVar(&hostname, "hostname", defaultHostname, "Node Hostname")
	rootCmd.PersistentFlags().IntVar(&serverPort, "server-port", 10080, "Server TCP Port")
	rootCmd.PersistentFlags().IntVar(&clientPort, "client-port", 10081, "Client SOCKS5 Proxy Port")
	rootCmd.PersistentFlags().IntVar(&apiPort, "api-port", 10082, "RESTful API HTTP Port")
	rootCmd.PersistentFlags().StringVar(&listenAddr, "listen", "127.0.0.1", "Client Listen IP")
	rootCmd.PersistentFlags().StringVar(&advertise, "advertise", "", "mDNS Advertise IP")
	rootCmd.PersistentFlags().StringVar(&strategy, "strategy", "random", "Load balance strategy")
	rootCmd.PersistentFlags().StringVar(&downloadDir, "download-dir", "./downloads", "File transfer save directory")
	rootCmd.PersistentFlags().StringSliceVar(&nodes, "node", nil, "Explicit remote node IP:Port (e.g. 192.168.132.72:10080)")

	// run command
	runCmd := &cobra.Command{
		Use:   "run",
		Short: "Run MOPS proxy daemon in foreground",
		RunE: func(cmd *cobra.Command, args []string) error {
			return runDaemon(Config{
				ServerPort:  serverPort,
				ClientPort:  clientPort,
				APIPort:     apiPort,
				ListenAddr:  listenAddr,
				Hostname:    hostname,
				Advertise:   advertise,
				Strategy:    strategy,
				DownloadDir: downloadDir,
			}, nodes)
		},
	}
	rootCmd.AddCommand(runCmd)

	// status command
	statusCmd := &cobra.Command{
		Use:   "status",
		Short: "Show cluster status in terminal",
		RunE: func(cmd *cobra.Command, args []string) error {
			statusData, nodes, err := fetchStatusFromAPI(apiPort)
			if err != nil {
				return fmt.Errorf("MOPS daemon service is not running: %w (start service via 'mops service start' or 'mops run')", err)
			}

			if !watch {
				fmt.Print(RenderStatus(nodes, statusData.Strategy, statusData.ClientPort, statusData.SpeedUp, statusData.SpeedDown))
				return nil
			}

			for {
				statusData, nodes, err := fetchStatusFromAPI(apiPort)
				if err != nil {
					fmt.Printf("\n[WARNING] Lost connection to daemon API: %v\n", err)
					return nil
				}
				fmt.Print("\033[H\033[2J") // Clear terminal screen
				fmt.Print(RenderStatus(nodes, statusData.Strategy, statusData.ClientPort, statusData.SpeedUp, statusData.SpeedDown))
				time.Sleep(1 * time.Second)
			}
		},
	}
	statusCmd.Flags().BoolVarP(&watch, "watch", "w", false, "Watch status periodically")
	rootCmd.AddCommand(statusCmd)

	// proxy command
	proxyCmd := &cobra.Command{
		Use:   "proxy [on|off|set <addr>|clear|status]",
		Short: "Manage Windows system proxy via REST API",
		Args:  cobra.RangeArgs(1, 2),
		RunE: func(cmd *cobra.Command, args []string) error {
			action := args[0]
			customAddr := ""
			if action == "set" {
				if len(args) < 2 {
					return fmt.Errorf("proxy set requires a target proxy address (e.g. mops proxy set 127.0.0.1:7890)")
				}
				customAddr = args[1]
			}
			err := controlSystemProxyViaAPI(apiPort, action, customAddr)
			if err != nil {
				return fmt.Errorf("failed to control system proxy: %w (ensure MOPS daemon/service is running)", err)
			}
			return nil
		},
	}
	rootCmd.AddCommand(proxyCmd)

	// client command
	clientCmd := &cobra.Command{
		Use:   "client [on|off|status]",
		Short: "Manage Client SOCKS5 Proxy listener via REST API",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			err := controlClientViaAPI(apiPort, args[0])
			if err != nil {
				return fmt.Errorf("failed to control client: %w (ensure MOPS daemon/service is running)", err)
			}
			return nil
		},
	}
	rootCmd.AddCommand(clientCmd)

	// server command
	serverCmd := &cobra.Command{
		Use:   "server [on|off|status]",
		Short: "Manage Server TCP Proxy listener via REST API",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			err := controlServerViaAPI(apiPort, args[0])
			if err != nil {
				return fmt.Errorf("failed to control server: %w (ensure MOPS daemon/service is running)", err)
			}
			return nil
		},
	}
	rootCmd.AddCommand(serverCmd)

	// service command
	serviceCmd := &cobra.Command{
		Use:   "service [install|update|uninstall|start|stop]",
		Short: "Manage MOPS as Windows Service",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			cfg := Config{
				ServerPort: serverPort,
				ClientPort: clientPort,
				APIPort:    apiPort,
				ListenAddr: listenAddr,
				Hostname:   hostname,
				Advertise:  advertise,
				Strategy:   strategy,
			}
			err := controlServiceViaAPI(apiPort, args[0], cfg)
			if err != nil {
				return err
			}
			fmt.Printf("Windows Service operation '%s' succeeded.\n", args[0])
			return nil
		},
	}
	rootCmd.AddCommand(serviceCmd)

	return rootCmd.Execute()
}

func runDaemon(cfg Config, explicitNodes []string) error {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	engine := NewEngine(cfg)
	if err := engine.Start(ctx); err != nil {
		return err
	}
	defer engine.Stop()

	for _, nStr := range explicitNodes {
		host, pStr, err := net.SplitHostPort(nStr)
		if err == nil {
			port, _ := strconv.Atoi(pStr)
			nodeID := fmt.Sprintf("REMOTE@%s:%d", host, port)
			engine.UpdateNode(&Node{
				ID:       nodeID,
				Hostname: "REMOTE-NODE",
				IP:       host,
				Port:     port,
				Role:     "Server",
				Status:   "ONLINE",
			})
		}
	}

	discovery := NewDiscovery(engine)
	if err := discovery.Start(ctx); err != nil {
		return err
	}
	defer discovery.Stop()

	fmt.Printf("MOPS Proxy running on Server :%d, Client SOCKS5 %s:%d, REST API :%d (Strategy: %s)\n",
		cfg.ServerPort, cfg.ListenAddr, cfg.ClientPort, cfg.APIPort, cfg.Strategy)
	if cfg.Advertise != "" {
		fmt.Printf("[INFO] Outbound LAN IP: %s (Specified via --advertise)\n", engine.GetAdvertiseIP())
	} else {
		fmt.Printf("[INFO] Outbound LAN IP: %s (Auto-detected physical interface)\n", engine.GetAdvertiseIP())
	}

	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)
	<-sigChan

	fmt.Println("\nShutting down MOPS daemon...")
	return nil
}
