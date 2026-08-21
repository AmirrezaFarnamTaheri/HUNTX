// Package main provides the WebAssembly compilation target for HUNTX client-side browser execution.
package main

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"strings"
)

func decodeBase64Subscription(input string) ([]string, error) {
	cleaned := strings.TrimSpace(input)
	if cleaned == "" {
		return []string{}, nil
	}
	decoded, err := base64.StdEncoding.DecodeString(cleaned)
	if err != nil {
		decoded, err = base64.RawStdEncoding.DecodeString(cleaned)
		if err != nil {
			return nil, fmt.Errorf("invalid base64 subscription: %w", err)
		}
	}
	lines := strings.Split(string(decoded), "\n")
	var result []string
	for _, l := range lines {
		trimmed := strings.TrimSpace(l)
		if trimmed != "" {
			result = append(result, trimmed)
		}
	}
	return result, nil
}

func processNodesJSON(input string) (string, error) {
	var nodes []map[string]any
	if err := json.Unmarshal([]byte(input), &nodes); err != nil {
		return "", err
	}
	var out bytes.Buffer
	enc := json.NewEncoder(&out)
	if err := enc.Encode(nodes); err != nil {
		return "", err
	}
	return out.String(), nil
}
