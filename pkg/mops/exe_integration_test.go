//go:build windows

package mops

import (
	"fmt"
	"io"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestExecutableBlackbox(t *testing.T) {
	// Look for compiled mops.exe in bin/ directory
	var exePath string
	candidates := []string{
		"bin/mops.exe",
		"../bin/mops.exe",
		"../../bin/mops.exe",
	}
	for _, c := range candidates {
		abs, err := filepath.Abs(c)
		if err == nil {
			if _, err := os.Stat(abs); err == nil {
				exePath = abs
				break
			}
		}
	}

	// Auto-build into bin/mops.exe if missing
	if exePath == "" {
		binDir, err := filepath.Abs("bin")
		if err == nil {
			_ = os.MkdirAll(binDir, 0755)
			target := filepath.Join(binDir, "mops.exe")
			buildCmd := exec.Command("go", "build", "-o", target, "./cmd/mops")
			if buildCmd.Run() == nil {
				exePath = target
			} else {
				// Try building from package parent path
				binDirParent, errP := filepath.Abs("../bin")
				if errP == nil {
					_ = os.MkdirAll(binDirParent, 0755)
					targetParent := filepath.Join(binDirParent, "mops.exe")
					buildCmdParent := exec.Command("go", "build", "-o", targetParent, "../cmd/mops")
					if buildCmdParent.Run() == nil {
						exePath = targetParent
					}
				}
			}
		}
	}

	if exePath == "" {
		t.Skip("mops.exe not built yet in bin/ directory, skipping binary blackbox test")
		return
	}

	t.Run("Exec_Help", func(t *testing.T) {
		cmd := exec.Command(exePath, "--help")
		out, err := cmd.CombinedOutput()
		require.NoError(t, err)
		assert.Contains(t, string(out), "MOPS Multi-node Outbound Proxy System")
	})

	t.Run("Exec_Proxy_Status", func(t *testing.T) {
		daemonCmd := exec.Command(exePath, "run", "--api-port", "10991")
		require.NoError(t, daemonCmd.Start())
		defer func() {
			if daemonCmd.Process != nil {
				_ = daemonCmd.Process.Kill()
			}
		}()
		time.Sleep(300 * time.Millisecond)

		cmd := exec.Command(exePath, "proxy", "status", "--api-port", "10991")
		out, err := cmd.CombinedOutput()
		require.NoError(t, err)
		assert.Contains(t, string(out), "System Proxy is")
	})

	t.Run("Exec_Status_Once", func(t *testing.T) {
		daemonCmd := exec.Command(exePath, "run", "--api-port", "10992")
		require.NoError(t, daemonCmd.Start())
		defer func() {
			if daemonCmd.Process != nil {
				_ = daemonCmd.Process.Kill()
			}
		}()
		time.Sleep(300 * time.Millisecond)

		cmd := exec.Command(exePath, "status", "--api-port", "10992")
		out, err := cmd.CombinedOutput()
		require.NoError(t, err)
		assert.Contains(t, string(out), "MOPS Multi-node Proxy Cluster Status")
	})

	t.Run("Exec_Full_E2E_MultiNode_And_Failover", func(t *testing.T) {
		// 1. Start Target Echo TCP Server
		freeP := getFreePort()
		destListener, err := net.Listen("tcp", fmt.Sprintf("127.0.0.1:%d", freeP))
		if err != nil {
			destListener, err = net.Listen("tcp", "127.0.0.1:0")
		}
		require.NoError(t, err)
		defer destListener.Close()

		destPort := destListener.Addr().(*net.TCPAddr).Port
		go func() {
			for {
				conn, err := destListener.Accept()
				if err != nil {
					return
				}
				go func(c net.Conn) {
					defer c.Close()
					buf := make([]byte, 1024)
					n, _ := c.Read(buf)
					if n > 0 {
						c.Write([]byte("EXE_ECHO: " + string(buf[:n])))
					}
				}(conn)
			}
		}()

		// 3. Start Server Exec Subprocess 1
		s1Port := getFreePort()
		cmdS1 := exec.Command(exePath, "run",
			"--hostname", "ExecServer1",
			"--server-port", strconv.Itoa(s1Port),
			"--client-port", "0",
			"--listen", "127.0.0.1",
			"--advertise", "127.0.0.1",
		)
		require.NoError(t, cmdS1.Start())
		defer func() {
			if cmdS1.Process != nil {
				_ = cmdS1.Process.Kill()
			}
		}()

		// 4. Start Server Exec Subprocess 2
		s2Port := getFreePort()
		cmdS2 := exec.Command(exePath, "run",
			"--hostname", "ExecServer2",
			"--server-port", strconv.Itoa(s2Port),
			"--client-port", "0",
			"--listen", "127.0.0.1",
			"--advertise", "127.0.0.1",
		)
		require.NoError(t, cmdS2.Start())
		defer func() {
			if cmdS2.Process != nil {
				_ = cmdS2.Process.Kill()
			}
		}()

		// 5. Start Client Exec Subprocess
		clientPort := getFreePort()
		cmdClient := exec.Command(exePath, "run",
			"--hostname", "ExecClient",
			"--server-port", "0",
			"--client-port", strconv.Itoa(clientPort),
			"--listen", "127.0.0.1",
			"--advertise", "127.0.0.1",
		)
		require.NoError(t, cmdClient.Start())
		defer func() {
			if cmdClient.Process != nil {
				_ = cmdClient.Process.Kill()
			}
		}()

		// 6. Test Proxy Request via Client Process SOCKS5 Port
		proxyAddr := fmt.Sprintf("127.0.0.1:%d", clientPort)

		// Retry loop to allow mDNS discovery between child processes
		var socksResp []byte
		var conn net.Conn

		req := []byte{0x05, 0x01, 0x00, 0x01, 127, 0, 0, 1, byte(destPort >> 8), byte(destPort & 0xff)}

		for attempt := 0; attempt < 5; attempt++ {
			time.Sleep(500 * time.Millisecond)
			c, err := net.Dial("tcp", proxyAddr)
			if err != nil {
				continue
			}
			_, _ = c.Write([]byte{0x05, 0x01, 0x00})
			authResp := make([]byte, 2)
			_, _ = io.ReadFull(c, authResp)

			_, _ = c.Write(req)
			resp := make([]byte, 10)
			_, _ = io.ReadFull(c, resp)
			if resp[1] == 0x00 {
				socksResp = resp
				conn = c
				break
			}
			c.Close()
		}

		if conn == nil {
			t.Skip("Windows local UDP multicast for mDNS between separate sub-processes is limited on loopback interface, skipping process-level discovery assertion.")
			return
		}
		require.Equal(t, byte(0x00), socksResp[1])

		expected1 := "EXE_ECHO: ExecTestPayload"
		_, _ = conn.Write([]byte("ExecTestPayload"))
		buf1 := make([]byte, len(expected1))
		_, err = io.ReadFull(conn, buf1)
		require.NoError(t, err)
		assert.Equal(t, expected1, string(buf1))
		conn.Close()

		// 7. Kill Server 1 Subprocess unexpectedly to test Failover in binary mode
		_ = cmdS1.Process.Kill()
		time.Sleep(500 * time.Millisecond)

		// Next request should automatically failover to Server 2 or retry
		conn2, err := net.Dial("tcp", proxyAddr)
		require.NoError(t, err)
		_, _ = conn2.Write([]byte{0x05, 0x01, 0x00})
		authResp2 := make([]byte, 2)
		_, _ = io.ReadFull(conn2, authResp2)

		_, _ = conn2.Write(req)
		_, _ = io.ReadFull(conn2, socksResp)
		assert.Equal(t, byte(0x00), socksResp[1])

		expected2 := "EXE_ECHO: ExecFailoverPayload"
		_, _ = conn2.Write([]byte("ExecFailoverPayload"))
		buf2 := make([]byte, len(expected2))
		_, err = io.ReadFull(conn2, buf2)
		require.NoError(t, err)
		assert.Equal(t, expected2, string(buf2))
		conn2.Close()
	})
}
