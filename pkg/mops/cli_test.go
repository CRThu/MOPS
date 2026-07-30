package mops

import (
	"bytes"
	"os"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
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
	oldArgs := os.Args
	defer func() { os.Args = oldArgs }()

	// Test proxy status
	os.Args = []string{"mops", "proxy", "status"}
	err := Execute()
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

	// Run status non-watch mode
	os.Args = []string{"mops", "status", "--client-port", "10899"}

	go func() {
		time.Sleep(200 * time.Millisecond)
	}()

	err := Execute()
	assert.NoError(t, err)
}
