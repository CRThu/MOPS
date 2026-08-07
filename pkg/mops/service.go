package mops

import (
	"context"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/kardianos/service"
	"golang.org/x/sys/windows"
)

type program struct {
	engine *Engine
	disc   *Discovery
	ctx    context.Context
	cancel context.CancelFunc
}

func (p *program) Start(s service.Service) error {
	p.ctx, p.cancel = context.WithCancel(context.Background())
	go p.run()
	return nil
}

func (p *program) run() {
	if err := p.engine.Start(p.ctx); err != nil {
		return
	}
	_ = p.disc.Start(p.ctx)
}

func (p *program) Stop(s service.Service) error {
	if p.cancel != nil {
		p.cancel()
	}
	if p.disc != nil {
		p.disc.Stop()
	}
	if p.engine != nil {
		p.engine.Stop()
	}
	return nil
}

// IsAdministrator checks if the current process running with elevated privileges.
func IsAdministrator() bool {
	var sid *windows.SID
	err := windows.AllocateAndInitializeSid(
		&windows.SECURITY_NT_AUTHORITY,
		2,
		windows.SECURITY_BUILTIN_DOMAIN_RID,
		windows.DOMAIN_ALIAS_RID_ADMINS,
		0, 0, 0, 0, 0, 0,
		&sid,
	)
	if err != nil {
		return false
	}
	defer windows.FreeSid(sid)

	token := windows.Token(0)
	member, err := token.IsMember(sid)
	if err != nil {
		return false
	}
	return member
}

// ControlService handles service install, uninstall, start, stop.
func ControlService(action string, cfg Config) error {
	if (action == "install" || action == "uninstall" || action == "start" || action == "stop" || action == "update") && !IsAdministrator() {
		return fmt.Errorf("administrative privileges required for service operation '%s'. Please run terminal as Administrator or accept UAC prompt", action)
	}

	svcConfig := &service.Config{
		Name:        "mops",
		DisplayName: "MOPS Proxy Service",
		Description: "Multi-node Outbound Proxy System Service for Windows",
	}

	eng := NewEngine(cfg)
	disc := NewDiscovery(eng)
	prg := &program{
		engine: eng,
		disc:   disc,
	}

	switch action {
	case "install":
		sCheck, sErr := service.New(prg, svcConfig)
		if sErr == nil {
			if _, statusErr := sCheck.Status(); statusErr == nil {
				fmt.Println("[INFO] Service 'mops' is already installed. Use 'mops service update' to overwrite and update.")
				return nil
			}
		}

		pf := os.Getenv("ProgramFiles")
		if pf == "" {
			pf = `C:\Program Files`
		}
		targetDir := filepath.Join(pf, "MOPS")
		targetExe := filepath.Join(targetDir, "mops.exe")

		exePath, err := os.Executable()
		if err == nil && exePath != "" {
			cleanCur, _ := filepath.Abs(exePath)
			cleanDst, _ := filepath.Abs(targetExe)
			if !strings.EqualFold(cleanCur, cleanDst) {
				if err := os.MkdirAll(targetDir, 0755); err == nil {
					_ = copyFileWithOverwrite(cleanCur, cleanDst)
					svcConfig.Executable = cleanDst
				}
			} else {
				svcConfig.Executable = cleanDst
			}
		}

		s, err := service.New(prg, svcConfig)
		if err != nil {
			return fmt.Errorf("failed to initialize Windows service: %w", err)
		}
		return s.Install()

	case "update":
		pf := os.Getenv("ProgramFiles")
		if pf == "" {
			pf = `C:\Program Files`
		}
		targetDir := filepath.Join(pf, "MOPS")
		targetExe := filepath.Join(targetDir, "mops.exe")

		// Stop running service if already exists to unlock executable file
		if s, sErr := service.New(prg, svcConfig); sErr == nil {
			if status, err := s.Status(); err == nil && status == service.StatusRunning {
				_ = s.Stop()
				time.Sleep(500 * time.Millisecond) // wait for process file handle release
			}
		}

		exePath, err := os.Executable()
		if err == nil && exePath != "" {
			cleanCur, _ := filepath.Abs(exePath)
			cleanDst, _ := filepath.Abs(targetExe)
			if !strings.EqualFold(cleanCur, cleanDst) {
				if err := os.MkdirAll(targetDir, 0755); err == nil {
					_ = copyFileWithOverwrite(cleanCur, cleanDst)
					svcConfig.Executable = cleanDst
				}
			} else {
				svcConfig.Executable = cleanDst
			}
		}

		s, err := service.New(prg, svcConfig)
		if err != nil {
			return fmt.Errorf("failed to initialize Windows service: %w", err)
		}
		_ = s.Uninstall() // Clean old service registration if exists
		if err := s.Install(); err != nil {
			return fmt.Errorf("failed to re-install upgraded service: %w", err)
		}
		return s.Start()

	case "uninstall":
		s, err := service.New(prg, svcConfig)
		if err != nil {
			return fmt.Errorf("failed to initialize Windows service: %w", err)
		}
		return s.Uninstall()

	case "start":
		s, err := service.New(prg, svcConfig)
		if err != nil {
			return fmt.Errorf("failed to initialize Windows service: %w", err)
		}
		return s.Start()

	case "stop":
		s, err := service.New(prg, svcConfig)
		if err != nil {
			return fmt.Errorf("failed to initialize Windows service: %w", err)
		}
		return s.Stop()

	case "run":
		s, err := service.New(prg, svcConfig)
		if err != nil {
			return fmt.Errorf("failed to initialize Windows service: %w", err)
		}
		return s.Run()

	default:
		return fmt.Errorf("unknown service command: %s", action)
	}
}

func copyFileWithOverwrite(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()

	out, err := os.OpenFile(dst, os.O_RDWR|os.O_CREATE|os.O_TRUNC, 0755)
	if err != nil {
		return err
	}
	defer out.Close()

	_, err = io.Copy(out, in)
	return err
}
