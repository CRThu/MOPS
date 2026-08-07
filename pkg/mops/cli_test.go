package mops

import (
	"bytes"
	"context"
	"os"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestCLIVersionAndHelp(t *testing.T) {
	// Test CLI with help flag
	oldArgs := os.Args
	defer func() { os.Args = oldArgs }()

	os.Args = []string{"mops", "--help"}

	var buf bytes.Buffer
	err := Execute()
	assert.NoError(t, err)
	assert.Nil(t, buf.Bytes())
}

func TestCLIProxySubcommand(t *testing.T) {
	origInfo, _ := GetSystemProxyInfo()
	defer func() {
		_ = RestoreSystemProxyInfo(origInfo)
	}()

	oldArgs := os.Args
	defer func() { os.Args = oldArgs }()

	// Start engine for REST API
	apiPort := 10082
	engine := NewEngine(Config{
		APIPort:    apiPort,
		ClientPort: 10081,
		ServerPort: 10080,
	})
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	require.NoError(t, engine.Start(ctx))
	defer engine.Stop()

	// Test proxy status
	os.Args = []string{"mops", "proxy", "status"}
	err := Execute()
	assert.NoError(t, err)

	// Test proxy set custom address
	os.Args = []string{"mops", "proxy", "set", "127.0.0.1:7890"}
	err = Execute()
	assert.NoError(t, err)

	// Test proxy clear
	os.Args = []string{"mops", "proxy", "clear"}
	err = Execute()
	assert.NoError(t, err)

	// Test proxy invalid action
	os.Args = []string{"mops", "proxy", "invalid_action"}
	err = Execute()
	assert.Error(t, err)
}

func TestCLIServiceSubcommandInvalid(t *testing.T) {
	oldArgs := os.Args
	defer func() { os.Args = oldArgs }()

	os.Args = []string{"mops", "service", "invalid_action"}
	err := Execute()
	assert.Error(t, err)
}

func TestCLIStatusSubcommand(t *testing.T) {
	oldArgs := os.Args
	defer func() { os.Args = oldArgs }()

	apiPort := 10082
	engine := NewEngine(Config{
		APIPort:    apiPort,
		ClientPort: 10081,
		ServerPort: 10080,
	})
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	require.NoError(t, engine.Start(ctx))
	defer engine.Stop()

	// Run status non-watch mode
	os.Args = []string{"mops", "status", "--api-port", "10082"}

	err := Execute()
	assert.NoError(t, err)
}

func TestCLIClientSubcommand(t *testing.T) {
	oldArgs := os.Args
	defer func() { os.Args = oldArgs }()

	apiPort := 10082
	engine := NewEngine(Config{
		APIPort:    apiPort,
		ClientPort: 10081,
		ServerPort: 10080,
	})
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	require.NoError(t, engine.Start(ctx))
	defer engine.Stop()

	// Test client status, off, on
	os.Args = []string{"mops", "--api-port", "10082", "client", "status"}
	assert.NoError(t, Execute())

	os.Args = []string{"mops", "--api-port", "10082", "client", "off"}
	assert.NoError(t, Execute())

	os.Args = []string{"mops", "--api-port", "10082", "client", "on"}
	assert.NoError(t, Execute())
}

func TestCLIServerSubcommand(t *testing.T) {
	oldArgs := os.Args
	defer func() { os.Args = oldArgs }()

	apiPort := 10082
	engine := NewEngine(Config{
		APIPort:    apiPort,
		ClientPort: 10081,
		ServerPort: 10080,
	})
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	require.NoError(t, engine.Start(ctx))
	defer engine.Stop()

	// Test server status, off, on
	os.Args = []string{"mops", "--api-port", "10082", "server", "status"}
	assert.NoError(t, Execute())

	os.Args = []string{"mops", "--api-port", "10082", "server", "off"}
	assert.NoError(t, Execute())

	os.Args = []string{"mops", "--api-port", "10082", "server", "on"}
	assert.NoError(t, Execute())
}
