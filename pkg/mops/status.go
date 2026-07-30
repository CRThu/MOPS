package mops

import (
	"bytes"
	"fmt"
	"strconv"
	"text/tabwriter"
)

// FormatBytes formats byte counts into human readable strings.
func FormatBytes(b uint64) string {
	const unit = 1024
	if b < unit {
		return fmt.Sprintf("%d B", b)
	}
	div, exp := int64(unit), 0
	for n := b / unit; n >= unit; n /= unit {
		div *= unit
		exp++
	}
	return fmt.Sprintf("%.1f %cB", float64(b)/float64(div), "KMGTPE"[exp])
}

// FormatSpeed formats byte rate into B/s, KB/s, MB/s, or GB/s.
func FormatSpeed(speedBps float64) string {
	if speedBps < 1024 {
		return fmt.Sprintf("%.1f B/s", speedBps)
	} else if speedBps < 1024*1024 {
		return fmt.Sprintf("%.1f KB/s", speedBps/1024)
	} else if speedBps < 1024*1024*1024 {
		return fmt.Sprintf("%.2f MB/s", speedBps/(1024*1024))
	}
	return fmt.Sprintf("%.2f GB/s", speedBps/(1024*1024*1024))
}

// RenderStatus renders the Tailscale-style cluster status table.
func RenderStatus(nodes []*Node, strategy string, clientPort int, speedUp, speedDown float64) string {
	var buf bytes.Buffer

	activeCount := 0
	for _, n := range nodes {
		if n.Status == "ONLINE" {
			activeCount++
		}
	}

	buf.WriteString("# MOPS Multi-node Proxy Cluster Status (Windows)\n")
	buf.WriteString(fmt.Sprintf("Strategy: %s | Active Nodes: %d/%d | Local Proxy: 127.0.0.1:%d\n\n",
		strategy, activeCount, len(nodes), clientPort))

	tw := tabwriter.NewWriter(&buf, 0, 0, 3, ' ', 0)
	fmt.Fprintln(tw, "ID\tHOSTNAME\tIP\tPORT\tROLE\tSTATUS\tACTIVE CONNS\tTRAFFIC (UP / DOWN)")
	fmt.Fprintln(tw, "---\t--------\t--\t----\t----\t------\t------------\t-------------------")

	for _, n := range nodes {
		idStr := n.ID
		if n.IsMe {
			idStr += " (me)"
		}

		connsStr := fmt.Sprintf("%d conns", n.ActiveConn)
		trafficStr := fmt.Sprintf("%s / %s", FormatBytes(n.BytesUp), FormatBytes(n.BytesDown))

		fmt.Fprintf(tw, "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n",
			idStr,
			n.Hostname,
			n.IP,
			strconv.Itoa(n.Port),
			n.Role,
			n.Status,
			connsStr,
			trafficStr,
		)
	}

	tw.Flush()

	buf.WriteString(fmt.Sprintf("\nCurrent Total Speed: ▲ %s | ▼ %s\n", FormatSpeed(speedUp), FormatSpeed(speedDown)))

	return buf.String()
}

