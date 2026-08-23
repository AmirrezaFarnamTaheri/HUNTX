package main

import "testing"

func TestLoadNodesRequiresValidatedConfiguration(t *testing.T) {
	t.Setenv("HUNTX_DAEMON_NODES_JSON", "")
	if _, err := loadNodes(); err == nil {
		t.Fatal("expected missing nodes configuration to fail")
	}

	t.Setenv("HUNTX_DAEMON_NODES_JSON", `[{"id":"n1","protocol":"http","server":"127.0.0.1","port":443,"alive":true}]`)
	nodes, err := loadNodes()
	if err != nil || len(nodes) != 1 || nodes[0].ID != "n1" {
		t.Fatalf("unexpected nodes result: %#v, %v", nodes, err)
	}
}

func TestLoadNodesRejectsUnsafeAndUnsupportedProxyInputs(t *testing.T) {
	t.Setenv("HUNTX_DAEMON_NODES_JSON", `[{"id":"n1","protocol":"vless","server":"example.com","port":443,"alive":true}]`)
	if _, err := loadNodes(); err == nil {
		t.Fatal("expected unsupported protocol to fail")
	}
	t.Setenv("HUNTX_DAEMON_NODES_JSON", `[{"id":"n1","protocol":"http","server":"bad\";DIRECT","port":443,"alive":true}]`)
	if _, err := loadNodes(); err == nil {
		t.Fatal("expected unsafe host to fail")
	}
}
