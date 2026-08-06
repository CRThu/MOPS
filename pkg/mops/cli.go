package mops

import (
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

// Execute builds and executes the CLI commands.
func Execute() error {
	var (
		serverPort int
		clientPort int
		apiPort    int
		listenAddr string
		advertise  string
		strategy   string
		nodes      []string
		watch      bool
	)

	defaultHostname, _ := os.Hostname()
	if defaultHostname == "" {
		defaultHostname = "Windows-PC"
	}
	var hostname string

	rootCmd := &cobra.Command{
		Use:   "mops",
		Short: "MOPS Multi-node Outbound Proxy System",
		RunE: func(cmd *cobra.Command, args []string) error {
			return runDaemon(Config{
				ServerPort: serverPort,
				ClientPort: clientPort,
				APIPort:    apiPort,
				ListenAddr: listenAddr,
				Hostname:   hostname,
				Advertise:  advertise,
				Strategy:   strategy,
			}, nodes)
		},
	}

	rootCmd.PersistentFlags().StringVar(&hostname, "hostname", defaultHostname, "Node Hostname")
	rootCmd.PersistentFlags().IntVar(&serverPort, "server-port", 10080, "Server TCP Port")
	rootCmd.PersistentFlags().IntVar(&clientPort, "client-port", 10081, "Client SOCKS5 Proxy Port")
	rootCmd.PersistentFlags().IntVar(&apiPort, "api-port", 10082, "RESTful API HTTP Port")
	rootCmd.PersistentFlags().StringVar(&listenAddr, "listen", "127.0.0.1", "Client Listen IP")
	rootCmd.PersistentFlags().StringVar(&advertise, "advertise", "", "mDNS Advertise IP")
	rootCmd.PersistentFlags().StringVar(&strategy, "strategy", "random", "Load balance strategy")
	rootCmd.PersistentFlags().StringSliceVar(&nodes, "node", nil, "Explicit remote node IP:Port (e.g. 192.168.132.72:10080)")

	// run command
	runCmd := &cobra.Command{
		Use:   "run",
		Short: "Run MOPS proxy daemon in foreground",
		RunE: func(cmd *cobra.Command, args []string) error {
			return runDaemon(Config{
				ServerPort: serverPort,
				ClientPort: clientPort,
				APIPort:    apiPort,
				ListenAddr: listenAddr,
				Hostname:   hostname,
				Advertise:  advertise,
				Strategy:   strategy,
			}, nodes)
		},
	}
	rootCmd.AddCommand(runCmd)

	// status command
	statusCmd := &cobra.Command{
		Use:   "status",
		Short: "Show cluster status in terminal",
		RunE: func(cmd *cobra.Command, args []string) error {
			// 1. Try to fetch status from running daemon via REST API first
			statusData, nodes, err := fetchStatusFromAPI(apiPort)
			if err == nil {
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
			}

			// 2. Fallback to standalone scanner if API is unreachable
			cfg := Config{
				ServerPort: serverPort,
				ClientPort: clientPort,
				APIPort:    apiPort,
				ListenAddr: listenAddr,
				Hostname:   hostname,
				Advertise:  advertise,
				Strategy:   strategy,
			}
			engine := NewEngine(cfg)
			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()

			_ = engine.Start(ctx)
			discovery := NewDiscovery(engine)
			_ = discovery.Start(ctx)

			if !watch {
				// Single status check: browse mDNS for 1.5s to gather all LAN nodes
				time.Sleep(1500 * time.Millisecond)
				nodes := engine.GetNodes()
				speedUp, speedDown := engine.GetSpeed()
				fmt.Print(RenderStatus(nodes, strategy, clientPort, speedUp, speedDown))
				return nil
			}

			// Watch mode: continuously poll and refresh
			for {
				nodes := engine.GetNodes()
				speedUp, speedDown := engine.GetSpeed()

				fmt.Print("\033[H\033[2J") // Clear terminal screen
				fmt.Print(RenderStatus(nodes, strategy, clientPort, speedUp, speedDown))

				time.Sleep(1 * time.Second)
			}
			discovery.Stop()
			engine.Stop()
			return nil
		},
	}
	statusCmd.Flags().BoolVarP(&watch, "watch", "w", false, "Watch status periodically")
	rootCmd.AddCommand(statusCmd)

	// proxy command
	proxyCmd := &cobra.Command{
		Use:   "proxy [on|off|status]",
		Short: "Manage Windows system proxy",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			switch args[0] {
			case "on":
				addr := fmt.Sprintf("127.0.0.1:%d", clientPort)
				err := SetSystemProxy(true, addr)
				if err != nil {
					return err
				}
				fmt.Printf("Windows System Proxy enabled -> %s\n", addr)
			case "off":
				err := SetSystemProxy(false, "")
				if err != nil {
					return err
				}
				fmt.Println("Windows System Proxy disabled.")
			case "status":
				enabled, addr, err := GetSystemProxyStatus()
				if err != nil {
					return err
				}
				if enabled {
					fmt.Printf("System Proxy is ON -> %s\n", addr)
				} else {
					fmt.Println("System Proxy is OFF")
				}
			default:
				return fmt.Errorf("invalid action: %s. Use on, off, or status", args[0])
			}
			return nil
		},
	}
	rootCmd.AddCommand(proxyCmd)

	// service command
	serviceCmd := &cobra.Command{
		Use:   "service [install|uninstall|start|stop]",
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
			err := ControlService(args[0], cfg)
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
