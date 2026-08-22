//go:build js && wasm

package main

import (
	"syscall/js"
)

func jsDecodeSubscription(this js.Value, args []js.Value) any {
	if len(args) < 1 {
		return map[string]any{"error": "missing payload argument", "lines": []any{}}
	}
	payload := args[0].String()
	lines, err := decodeBase64Subscription(payload)
	if err != nil {
		return map[string]any{"error": err.Error(), "lines": []any{}}
	}
	jsLines := make([]any, len(lines))
	for i, l := range lines {
		jsLines[i] = l
	}
	return map[string]any{"lines": jsLines, "count": len(lines)}
}

func main() {
	c := make(chan struct{}, 0)
	js.Global().Set("huntx_decode_subscription", js.FuncOf(jsDecodeSubscription))
	<-c
}
