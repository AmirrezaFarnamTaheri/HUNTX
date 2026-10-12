package releasemanifest

import (
	"encoding/json"
	"fmt"
	"path/filepath"
	"strings"
)

// ValidateClientJSON enforces the import contract for named subscription and
// profile artifacts. Generic JSON datasets are checked for syntax only.
func ValidateClientJSON(filename string, payload []byte) error {
	var root any
	if err := json.Unmarshal(payload, &root); err != nil {
		return fmt.Errorf("%s: invalid JSON: %w", filepath.Base(filename), err)
	}
	name := strings.ToLower(filepath.Base(filename))
	switch {
	case matchesJSONProduct(name, ".nekobox.json", "_nekobox.json"):
		if err := validateProxyNodeArray(root, "type"); err != nil {
			return fmt.Errorf("NekoBox %s: %w", name, err)
		}
	case matchesJSONProduct(name, ".singbox.nodes.json", "_singbox_nodes.json"):
		if err := validateOutboundsOnly(root, "type"); err != nil {
			return fmt.Errorf("sing-box node feed %s: %w", name, err)
		}
	case matchesJSONProduct(name, ".xray.nodes.json", "_xray_nodes.json"):
		if err := validateOutboundsOnly(root, "protocol"); err != nil {
			return fmt.Errorf("Xray node feed %s: %w", name, err)
		}
	case matchesJSONProduct(name, ".singbox.profile.json", "_singbox_profile.json") ||
		matchesJSONProduct(name, ".singbox.json", "_singbox.json"):
		if err := validateRunnableProfile(root, true); err != nil {
			return fmt.Errorf("sing-box profile %s: %w", name, err)
		}
	case matchesJSONProduct(name, ".xray.profile.json", "_xray_profile.json") ||
		matchesJSONProduct(name, ".xray.json", "_xray.json"):
		if err := validateRunnableProfile(root, false); err != nil {
			return fmt.Errorf("Xray profile %s: %w", name, err)
		}
	}
	return nil
}

func matchesJSONProduct(name, dotted, canonical string) bool {
	return strings.HasSuffix(name, dotted) || strings.HasSuffix(name, canonical)
}

func validateProxyNodeArray(root any, protocolKey string) error {
	nodes, ok := root.([]any)
	if !ok || len(nodes) == 0 {
		return fmt.Errorf("expected a nonempty top-level proxy node array")
	}
	tags := make(map[string]struct{}, len(nodes))
	for i, raw := range nodes {
		node, ok := raw.(map[string]any)
		if !ok {
			return fmt.Errorf("node %d is not an object", i)
		}
		protocol, ok := node[protocolKey].(string)
		if !ok || strings.TrimSpace(protocol) == "" {
			return fmt.Errorf("node %d lacks %s", i, protocolKey)
		}
		tag, ok := node["tag"].(string)
		if !ok || strings.TrimSpace(tag) == "" {
			return fmt.Errorf("node %d lacks tag", i)
		}
		if protocolKey == "type" {
			switch protocol {
			case "selector", "urltest", "direct", "block", "dns":
				return fmt.Errorf("node %d is a non-proxy helper: %s", i, protocol)
			}
		}
		if _, exists := tags[tag]; exists {
			return fmt.Errorf("node %d has duplicate tag %q", i, tag)
		}
		tags[tag] = struct{}{}
	}
	return nil
}

func validateOutboundsOnly(root any, protocolKey string) error {
	object, ok := root.(map[string]any)
	if !ok || len(object) != 1 {
		return fmt.Errorf("expected an outbounds-only object")
	}
	return validateProxyNodeArray(object["outbounds"], protocolKey)
}

func validateRunnableProfile(root any, singbox bool) error {
	object, ok := root.(map[string]any)
	if !ok {
		return fmt.Errorf("expected a profile object")
	}
	inbounds, ok := object["inbounds"].([]any)
	if !ok || len(inbounds) == 0 {
		return fmt.Errorf("runnable profile has no inbounds")
	}
	outbounds, ok := object["outbounds"].([]any)
	if !ok || len(outbounds) == 0 {
		return fmt.Errorf("runnable profile has no outbounds")
	}
	if singbox {
		if _, ok := object["dns"].(map[string]any); !ok {
			return fmt.Errorf("sing-box profile lacks DNS policy")
		}
		if _, ok := object["route"].(map[string]any); !ok {
			return fmt.Errorf("sing-box profile lacks routing policy")
		}
	}
	return nil
}
