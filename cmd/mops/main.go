package main

import (
	"fmt"
	"os"

	"mops/pkg/mops"
)

func main() {
	if err := mops.Execute(); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
}
