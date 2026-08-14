package mops

import (
	"context"
	"fmt"
	"net"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/grandcat/zeroconf"
)

const ServiceType = "_mops-proxy._tcp"

// Discovery handles mDNS registration and browsing.
type Discovery struct {
	engine   *Engine
	server   *zeroconf.Server
	resolver *zeroconf.Resolver
	mu       sync.Mutex
	cancel   context.CancelFunc
	paused   bool
}

// NewDiscovery creates a new mDNS discovery service.
func NewDiscovery(engine *Engine) *Discovery {
	d := &Discovery{
		engine: engine,
	}
	if engine != nil {
		engine.SetDiscovery(d)
	}
	return d
}

// Start registers local service and browses for remote nodes.
func (d *Discovery) Start(ctx context.Context) error {
	d.mu.Lock()
	defer d.mu.Unlock()

	ctx, cancel := context.WithCancel(ctx)
	d.cancel = cancel

	if d.engine != nil {
		d.engine.SetDiscovery(d)
	}

	// 1. Register mDNS Service
	d.registerServerLocked()

	// 2. Browse mDNS Services
	resolver, err := zeroconf.NewResolver(nil)
	if err != nil {
		return fmt.Errorf("failed to create zeroconf resolver: %w", err)
	}
	d.resolver = resolver

	entries := make(chan *zeroconf.ServiceEntry)
	go d.handleEntries(ctx, entries)

	if err := resolver.Browse(ctx, ServiceType, "local.", entries); err != nil {
		return fmt.Errorf("failed to browse zeroconf services: %w", err)
	}

	// Periodic mDNS re-query every 5s to discover new/late-joining LAN nodes
	go func() {
		ticker := time.NewTicker(5 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				_ = resolver.Browse(ctx, ServiceType, "local.", entries)
			}
		}
	}()

	return nil
}

func isVirtualInterface(name string) bool {
	lower := strings.ToLower(name)
	keywords := []string{
		"vethernet", "wsl", "tailscale", "zerotier", "mihomo", "clash",
		"tap", "tun", "vbox", "vmware", "virtual", "docker", "npcap",
		"loopback", "hyper-v",
	}
	for _, kw := range keywords {
		if strings.Contains(lower, kw) {
			return true
		}
	}
	return false
}

func isExcludedIP(ip net.IP) bool {
	if ip == nil {
		return true
	}
	ip4 := ip.To4()
	if ip4 == nil {
		return true
	}
	if ip4.IsLoopback() || ip4.IsLinkLocalUnicast() || ip4.IsMulticast() || ip4.IsUnspecified() {
		return true
	}
	// Exclude TUN/Clash range (198.18.0.0/15)
	if ip4[0] == 198 && (ip4[1] == 18 || ip4[1] == 19) {
		return true
	}
	// Exclude Link-Local (169.254.0.0/16)
	if ip4[0] == 169 && ip4[1] == 254 {
		return true
	}
	// Exclude Tailscale / CGNAT range (100.64.0.0/10)
	if ip4[0] == 100 && (ip4[1] >= 64 && ip4[1] <= 127) {
		return true
	}
	// Exclude Hyper-V / WSL / Docker virtual subnet (172.16.0.0/12)
	if ip4[0] == 172 && (ip4[1] >= 16 && ip4[1] <= 31) {
		return true
	}
	return false
}

func getMulticastInterfaces() []net.Interface {
	var validIfaces []net.Interface
	ifaces, err := net.Interfaces()
	if err != nil {
		return nil
	}
	for _, iface := range ifaces {
		if iface.Flags&net.FlagUp == 0 || iface.Flags&net.FlagLoopback != 0 || iface.Flags&net.FlagMulticast == 0 {
			continue
		}
		if isVirtualInterface(iface.Name) {
			continue
		}
		addrs, err := iface.Addrs()
		if err != nil {
			continue
		}
		hasValidIP := false
		for _, addr := range addrs {
			ipNet, ok := addr.(*net.IPNet)
			if !ok {
				continue
			}
			ip4 := ipNet.IP.To4()
			if ip4 != nil && !isExcludedIP(ip4) {
				hasValidIP = true
				break
			}
		}
		if hasValidIP {
			validIfaces = append(validIfaces, iface)
		}
	}
	return validIfaces
}

func (d *Discovery) registerServerLocked() {
	if d.server != nil || d.paused || d.engine == nil || d.engine.cfg.ServerPort <= 0 {
		return
	}

	var ips []string
	selfIP := ResolveAdvertiseIP(d.engine.cfg.Advertise)
	if selfIP != "" && selfIP != "127.0.0.1" {
		ips = append(ips, selfIP)
	}

	nodeID := fmt.Sprintf("%s@%s:%d", d.engine.cfg.Hostname, selfIP, d.engine.cfg.ServerPort)
	instanceName := fmt.Sprintf("%s-%d", d.engine.cfg.Hostname, d.engine.cfg.ServerPort)
	text := []string{
		"id=" + nodeID,
		"hostname=" + d.engine.cfg.Hostname,
		"port=" + strconv.Itoa(d.engine.cfg.ServerPort),
		"role=Server",
	}

	validIfaces := getMulticastInterfaces()
	srv, err := zeroconf.Register(
		instanceName,
		ServiceType,
		"local.",
		d.engine.cfg.ServerPort,
		text,
		validIfaces,
	)
	if err == nil {
		d.server = srv
	}
}

// PauseAdvertise pauses the local mDNS service broadcast (e.g. when disconnected from internet).
func (d *Discovery) PauseAdvertise() {
	d.mu.Lock()
	defer d.mu.Unlock()

	d.paused = true
	if d.server != nil {
		d.server.Shutdown()
		d.server = nil
	}
}

// ResumeAdvertise resumes the local mDNS service broadcast (e.g. when internet is restored).
func (d *Discovery) ResumeAdvertise() {
	d.mu.Lock()
	defer d.mu.Unlock()

	d.paused = false
	d.registerServerLocked()
}

// IsPaused returns whether local mDNS service broadcast is currently paused.
func (d *Discovery) IsPaused() bool {
	d.mu.Lock()
	defer d.mu.Unlock()
	return d.paused
}

// Stop shuts down the mDNS service registration and browser.
func (d *Discovery) Stop() {
	d.mu.Lock()
	defer d.mu.Unlock()

	if d.cancel != nil {
		d.cancel()
	}
	if d.server != nil {
		d.server.Shutdown()
		d.server = nil
	}
}

func (d *Discovery) handleEntries(ctx context.Context, entries <-chan *zeroconf.ServiceEntry) {
	for {
		select {
		case <-ctx.Done():
			return
		case entry, ok := <-entries:
			if !ok {
				return
			}
			node := parseServiceEntry(entry)
			if node != nil {
				selfIP := ResolveAdvertiseIP(d.engine.cfg.Advertise)
				isSelf := (node.IP == selfIP || node.IP == "127.0.0.1") && node.Port == d.engine.cfg.ServerPort
				if !isSelf {
					fmt.Printf("[mDNS Auto-Discovered Node] Hostname: %s, IP: %s, Port: %d\n", node.Hostname, node.IP, node.Port)
					d.engine.UpdateNode(node)
				}
			}
		}
	}
}

func parseServiceEntry(entry *zeroconf.ServiceEntry) *Node {
	txtMap := make(map[string]string)
	for _, txt := range entry.Text {
		parts := strings.SplitN(txt, "=", 2)
		if len(parts) == 2 {
			txtMap[parts[0]] = parts[1]
		}
	}

	hostname := txtMap["hostname"]
	if hostname == "" {
		hostname = entry.Instance
	}

	port := entry.Port
	if pStr, ok := txtMap["port"]; ok {
		if p, err := strconv.Atoi(pStr); err == nil {
			port = p
		}
	}

	ip := ""
	if len(entry.AddrIPv4) > 0 {
		for _, addrIPv4 := range entry.AddrIPv4 {
			ip4Str := addrIPv4.String()
			if strings.HasPrefix(ip4Str, "192.168.") || strings.HasPrefix(ip4Str, "10.") {
				ip = ip4Str
				break
			}
		}
		if ip == "" {
			for _, addrIPv4 := range entry.AddrIPv4 {
				if !isExcludedIP(addrIPv4) {
					ip = addrIPv4.String()
					break
				}
			}
		}
		if ip == "" {
			ip = entry.AddrIPv4[0].String()
		}
	} else if len(entry.AddrIPv6) > 0 {
		ip = entry.AddrIPv6[0].String()
	}

	if ip == "" {
		return nil
	}

	id := txtMap["id"]
	if id == "" {
		id = fmt.Sprintf("%s@%s:%d", hostname, ip, port)
	}

	return &Node{
		ID:       id,
		Hostname: hostname,
		IP:       ip,
		Port:     port,
		Role:     txtMap["role"],
		Status:   "ONLINE",
		LastSeen: time.Now(),
	}
}

// GetOutboundIP gets preferred LAN outbound IP of this machine, excluding virtual/TUN interfaces.
func GetOutboundIP() (string, error) {
	type candidate struct {
		ip    string
		score int
	}
	var candidates []candidate

	ifaces, err := net.Interfaces()
	if err == nil {
		for _, iface := range ifaces {
			if iface.Flags&net.FlagUp == 0 || iface.Flags&net.FlagLoopback != 0 {
				continue
			}
			isVirt := isVirtualInterface(iface.Name)
			addrs, aerr := iface.Addrs()
			if aerr != nil {
				continue
			}
			for _, addr := range addrs {
				ipNet, ok := addr.(*net.IPNet)
				if !ok {
					continue
				}
				ip4 := ipNet.IP.To4()
				if ip4 == nil || isExcludedIP(ip4) {
					continue
				}
				ipStr := ip4.String()
				score := 0
				if !isVirt {
					score += 100
				} else {
					score += 10
				}

				if strings.HasPrefix(ipStr, "192.168.") {
					score += 1000
				} else if strings.HasPrefix(ipStr, "10.") {
					score += 800
				} else if isPrivate172(ip4) {
					score += 10
				} else {
					score += 5
				}

				candidates = append(candidates, candidate{ip: ipStr, score: score})
			}
		}
	}

	bestIP := ""
	bestScore := -1
	for _, c := range candidates {
		if c.score > bestScore {
			bestScore = c.score
			bestIP = c.ip
		}
	}

	if bestIP != "" && bestScore > 20 {
		return bestIP, nil
	}

	// Fallback to UDP dial
	conn, err := net.Dial("udp", "8.8.8.8:80")
	if err == nil {
		defer conn.Close()
		localAddr, ok := conn.LocalAddr().(*net.UDPAddr)
		if ok {
			ip4 := localAddr.IP.To4()
			if ip4 != nil && !isExcludedIP(ip4) {
				return ip4.String(), nil
			}
		}
	}

	if bestIP != "" {
		return bestIP, nil
	}

	return "", fmt.Errorf("no valid outbound IP found")
}

func isPrivate172(ip net.IP) bool {
	return ip[0] == 172 && ip[1] >= 16 && ip[1] <= 31
}

// NetworkInterface defines metadata for a local network interface.
type NetworkInterface struct {
	Name      string `json:"name"`
	IP        string `json:"ip"`
	IsVirtual bool   `json:"is_virtual"`
}

// GetNetworkInterfaces returns a list of active local IPv4 network interfaces.
func GetNetworkInterfaces() []NetworkInterface {
	var result []NetworkInterface
	ifaces, err := net.Interfaces()
	if err != nil {
		return result
	}

	for _, iface := range ifaces {
		if iface.Flags&net.FlagUp == 0 || iface.Flags&net.FlagLoopback != 0 {
			continue
		}
		addrs, err := iface.Addrs()
		if err != nil {
			continue
		}
		for _, addr := range addrs {
			ipNet, ok := addr.(*net.IPNet)
			if !ok {
				continue
			}
			ip4 := ipNet.IP.To4()
			if ip4 == nil || ip4.IsLoopback() || ip4.IsMulticast() || ip4.IsUnspecified() {
				continue
			}
			result = append(result, NetworkInterface{
				Name:      iface.Name,
				IP:        ip4.String(),
				IsVirtual: isVirtualInterface(iface.Name),
			})
		}
	}
	return result
}

// IsIPValidOnLocalInterfaces checks if targetIP exists on current active local network interfaces.
func IsIPValidOnLocalInterfaces(targetIP string) bool {
	if targetIP == "" || targetIP == "127.0.0.1" {
		return false
	}
	for _, iface := range GetNetworkInterfaces() {
		if iface.IP == targetIP {
			return true
		}
	}
	return false
}

// GetIPByInterfaceName returns current IPv4 address of network interface by name (case-insensitive).
func GetIPByInterfaceName(ifaceName string) string {
	if ifaceName == "" {
		return ""
	}
	for _, iface := range GetNetworkInterfaces() {
		if strings.EqualFold(iface.Name, ifaceName) {
			return iface.IP
		}
	}
	return ""
}

// ResolveAdvertiseIP resolves configured Advertise value into active IPv4 address.
// Supports:
// 1. Interface name (e.g. "Wi-Fi", "以太网", "eth0") -> returns current dynamic IP of interface
// 2. Exact valid IPv4 address (e.g. "192.168.1.100") -> returns if valid on local interfaces
// 3. Empty or stale -> falls back to auto-detected outbound IP
func ResolveAdvertiseIP(adv string) string {
	if adv == "" || adv == "127.0.0.1" {
		ip, _ := GetOutboundIP()
		return ip
	}
	if ip := GetIPByInterfaceName(adv); ip != "" {
		return ip
	}
	if IsIPValidOnLocalInterfaces(adv) {
		return adv
	}
	ip, _ := GetOutboundIP()
	return ip
}

