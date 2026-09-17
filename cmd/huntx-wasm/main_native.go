//go:build !js || !wasm

package main

import (
	"fmt"
	"os"
)

// Keep native repository builds valid without implying a native WASM runtime.
func main() {
	fmt.Fprintln(os.Stderr, "huntx-wasm requires GOOS=js GOARCH=wasm and a JavaScript host")
	os.Exit(1)
}
