package mops

import (
	"context"
	"fmt"

	"github.com/kardianos/service"
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

// ControlService handles service install, uninstall, start, stop.
func ControlService(action string, cfg Config) error {
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

	s, err := service.New(prg, svcConfig)
	if err != nil {
		return fmt.Errorf("failed to initialize Windows service: %w", err)
	}

	switch action {
	case "install":
		return s.Install()
	case "uninstall":
		return s.Uninstall()
	case "start":
		return s.Start()
	case "stop":
		return s.Stop()
	case "run":
		return s.Run()
	default:
		return fmt.Errorf("unknown service command: %s", action)
	}
}
