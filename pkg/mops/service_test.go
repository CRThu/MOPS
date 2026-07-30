package mops

import (
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

func TestServiceProgram(t *testing.T) {
	eng := NewEngine(Config{
		ServerPort: getFreePort(),
		ClientPort: getFreePort(),
		ListenAddr: "127.0.0.1",
		Hostname:   "TestSvc",
		Advertise:  "127.0.0.1",
	})
	disc := NewDiscovery(eng)

	prg := &program{
		engine: eng,
		disc:   disc,
	}

	err := prg.Start(nil)
	assert.NoError(t, err)

	time.Sleep(50 * time.Millisecond)

	err = prg.Stop(nil)
	assert.NoError(t, err)
}

func TestControlServiceInvalidAction(t *testing.T) {
	cfg := Config{
		ServerPort: 10080,
		ClientPort: 10081,
	}
	err := ControlService("invalid_action", cfg)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "unknown service command")
}
