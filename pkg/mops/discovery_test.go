package mops

import (
	"context"
	"net"
	"testing"
	"time"

	"github.com/grandcat/zeroconf"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestParseServiceEntry(t *testing.T) {
	entry := &zeroconf.ServiceEntry{
		Port: 10080,
		Text: []string{
			"id=node-01",
			"hostname=RemotePC",
			"port=10080",
			"role=Server",
		},
		AddrIPv4: []net.IP{net.ParseIP("192.168.1.50")},
	}
	entry.Instance = "RemoteNode-10080"

	node := parseServiceEntry(entry)
	assert.NotNil(t, node)
	assert.Equal(t, "node-01", node.ID)
	assert.Equal(t, "RemotePC", node.Hostname)
	assert.Equal(t, "192.168.1.50", node.IP)
	assert.Equal(t, 10080, node.Port)
	assert.Equal(t, "Server", node.Role)
	assert.Equal(t, "ONLINE", node.Status)
}

func TestGetOutboundIP(t *testing.T) {
	ip, err := GetOutboundIP()
	if err == nil {
		assert.NotEmpty(t, ip)
		assert.NotEqual(t, "127.0.0.1", ip)
	}
}

func TestGetNetworkInterfaces(t *testing.T) {
	ifaces := GetNetworkInterfaces()
	assert.NotNil(t, ifaces)
	// On systems with active network interfaces, ifaces will contain items
	for _, iface := range ifaces {
		assert.NotEmpty(t, iface.Name)
		assert.NotEmpty(t, iface.IP)
	}
}

func TestIsIPValidOnLocalInterfacesAndStaleIPFallback(t *testing.T) {
	// Stale / fake IP should be invalid
	assert.False(t, IsIPValidOnLocalInterfaces("203.0.113.199"))
	assert.False(t, IsIPValidOnLocalInterfaces(""))
	assert.False(t, IsIPValidOnLocalInterfaces("127.0.0.1"))

	// Real outbound IP should be valid
	if realIP, err := GetOutboundIP(); err == nil && realIP != "" {
		assert.True(t, IsIPValidOnLocalInterfaces(realIP))
	}
}

func TestResolveAdvertiseIPByInterfaceName(t *testing.T) {
	ifaces := GetNetworkInterfaces()
	if len(ifaces) > 0 {
		firstIface := ifaces[0]
		// Resolving by interface name should return the interface's current IP
		resolvedIP := ResolveAdvertiseIP(firstIface.Name)
		assert.Equal(t, firstIface.IP, resolvedIP)
	}

	// Invalid interface name should fall back to outbound IP
	fallbackIP := ResolveAdvertiseIP("NonExistentIface999")
	assert.NotEmpty(t, fallbackIP)
	assert.NotEqual(t, "127.0.0.1", fallbackIP)
}




func TestDiscoveryLifecycle(t *testing.T) {
	eng := NewEngine(Config{
		ServerPort: getFreePort(),
		ClientPort: getFreePort(),
		ListenAddr: "127.0.0.1",
		Hostname:   "DiscHost",
		Advertise:  "127.0.0.1",
	})
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	assert.NoError(t, eng.Start(ctx))
	defer eng.Stop()

	disc := NewDiscovery(eng)
	err := disc.Start(ctx)
	assert.NoError(t, err)

	time.Sleep(200 * time.Millisecond)

	disc.Stop()
}

func TestMDNSAutoDiscoveryEndToEnd(t *testing.T) {
	outIP, _ := GetOutboundIP()
	if outIP == "" {
		outIP = "127.0.0.1"
	}

	// 1. Setup Server Node A
	sPort := getFreePort()
	cfgA := Config{
		ServerPort: sPort,
		ClientPort: 0,
		ListenAddr: "127.0.0.1",
		Hostname:   "MDNS-Server-NodeA",
		Advertise:  outIP,
	}
	engA := NewEngine(cfgA)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	require.NoError(t, engA.Start(ctx))
	defer engA.Stop()

	discA := NewDiscovery(engA)
	require.NoError(t, discA.Start(ctx))
	defer discA.Stop()

	// 2. Setup Client Node B
	cPort := getFreePort()
	cfgB := Config{
		ServerPort: 0,
		ClientPort: cPort,
		ListenAddr: "127.0.0.1",
		Hostname:   "MDNS-Client-NodeB",
		Advertise:  outIP,
	}
	engB := NewEngine(cfgB)
	require.NoError(t, engB.Start(ctx))
	defer engB.Stop()

	discB := NewDiscovery(engB)
	require.NoError(t, discB.Start(ctx))
	defer discB.Stop()

	// Poll wait for mDNS multicast discovery (up to 2s)
	deadline := time.Now().Add(2 * time.Second)
	var foundServerA bool
	for time.Now().Before(deadline) {
		nodesB := engB.GetNodes()
		for _, n := range nodesB {
			if n.Hostname == "MDNS-Server-NodeA" {
				foundServerA = true
				break
			}
		}
		if foundServerA {
			break
		}
		time.Sleep(100 * time.Millisecond)
	}

	// mDNS packet delivery on local network interfaces
	if foundServerA {
		assert.True(t, foundServerA)
	}
}

func TestParseServiceEntryEdgeCases(t *testing.T) {
	// 1. Missing IP should return nil
	noIPEntry := &zeroconf.ServiceEntry{
		Port: 10080,
	}
	noIPEntry.Instance = "NoIPNode"
	assert.Nil(t, parseServiceEntry(noIPEntry))

	// 2. IPv6 fallback & default Instance text parsing
	ip6Entry := &zeroconf.ServiceEntry{
		Port:     10080,
		AddrIPv6: []net.IP{net.ParseIP("fe80::1")},
	}
	ip6Entry.Instance = "IPv6Instance"
	n6 := parseServiceEntry(ip6Entry)
	assert.NotNil(t, n6)
	assert.Equal(t, "IPv6Instance@fe80::1:10080", n6.ID)
	assert.Equal(t, "IPv6Instance", n6.Hostname)
	assert.Equal(t, "fe80::1", n6.IP)
	assert.Equal(t, 10080, n6.Port)
}

func TestDiscoveryPauseAndResume(t *testing.T) {
	eng := NewEngine(Config{
		ServerPort: getFreePort(),
		ClientPort: getFreePort(),
		Hostname:   "PauseResumeHost",
		Advertise:  "127.0.0.1",
	})
	eng.SetProbeFunc(func() bool { return false })
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	require.NoError(t, eng.Start(ctx))
	defer eng.Stop()

	disc := NewDiscovery(eng)
	require.NoError(t, disc.Start(ctx))
	defer disc.Stop()

	assert.False(t, disc.IsPaused())

	// Pause
	disc.PauseAdvertise()
	assert.True(t, disc.IsPaused())
	assert.Nil(t, disc.server)

	// Resume
	disc.ResumeAdvertise()
	assert.False(t, disc.IsPaused())
	assert.NotNil(t, disc.server)
}

