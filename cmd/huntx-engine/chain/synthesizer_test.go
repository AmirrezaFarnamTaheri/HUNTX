package chain

import (
	"context"
	"testing"
	"time"
)

func createSampleNode(hash, proto, addr string, port int, country string, latency time.Duration, alive bool) Node {
	return Node{
		UniqueHash:  hash,
		RawURI:      proto + "://user@" + addr + ":443#" + country,
		Protocol:    proto,
		Address:     addr,
		Port:        port,
		CountryCode: country,
		Latency:     latency,
		Alive:       alive,
	}
}

func TestSynthesizerRejectsDeadNodes(t *testing.T) {
	engine := New(WithStrategy(StrategyLowestLatency))
	pool := []Node{
		createSampleNode("dead1", "vless", "1.1.1.1", 443, "US", 50*time.Millisecond, false),
		createSampleNode("dead2", "trojan", "2.2.2.2", 443, "DE", 60*time.Millisecond, false),
	}

	chains, err := engine.Synthesize(context.Background(), pool)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(chains) != 0 {
		t.Fatalf("expected 0 chains from dead nodes, got %d", len(chains))
	}
}

func TestSynthesizerLoopPrevention(t *testing.T) {
	engine := New(WithStrategy(StrategyLowestLatency))
	// Single node cannot form a loop with itself
	pool := []Node{
		createSampleNode("node1", "vless", "1.1.1.1", 443, "US", 50*time.Millisecond, true),
	}

	chains, err := engine.Synthesize(context.Background(), pool)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(chains) != 0 {
		t.Fatalf("expected 0 chains when pool has only 1 node, got %d", len(chains))
	}
}

func TestSynthesizerDomesticRelayInternationalExit(t *testing.T) {
	engine := New(
		WithStrategy(StrategyDomesticRelayInternationalExit),
		WithDomesticCountry("IR"),
		WithMaxLatencyCeiling(500*time.Millisecond),
	)

	pool := []Node{
		createSampleNode("relay1", "vless", "185.1.1.1", 443, "IR", 20*time.Millisecond, true),
		createSampleNode("exit1", "trojan", "142.250.1.1", 443, "DE", 80*time.Millisecond, true),
		createSampleNode("exit2", "shadowsocks", "104.16.1.1", 443, "US", 140*time.Millisecond, true),
		createSampleNode("domestic2", "vless", "185.2.2.2", 443, "IR", 25*time.Millisecond, true),
	}

	chains, err := engine.Synthesize(context.Background(), pool)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(chains) == 0 {
		t.Fatalf("expected synthesized chains, got 0")
	}

	for _, c := range chains {
		if c.Entry.CountryCode != "IR" {
			t.Errorf("expected entry relay in IR, got %s", c.Entry.CountryCode)
		}
		if c.Exit.CountryCode == "IR" {
			t.Errorf("expected exit node to be non-domestic, got %s", c.Exit.CountryCode)
		}
		if c.Entry.UniqueHash == c.Exit.UniqueHash {
			t.Errorf("entry and exit node must not be the same: %s", c.Entry.UniqueHash)
		}
	}
}

func TestSynthesizerLatencySortingAndCeiling(t *testing.T) {
	engine := New(
		WithStrategy(StrategyLowestLatency),
		WithMaxLatencyCeiling(300*time.Millisecond),
		WithMaxChains(5),
	)

	pool := []Node{
		createSampleNode("n1", "vless", "1.1.1.1", 443, "DE", 40*time.Millisecond, true),
		createSampleNode("n2", "trojan", "2.2.2.2", 443, "NL", 50*time.Millisecond, true),
		createSampleNode("n3", "vless", "3.3.3.3", 443, "US", 280*time.Millisecond, true),
	}

	chains, err := engine.Synthesize(context.Background(), pool)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(chains) == 0 {
		t.Fatalf("expected chains, got 0")
	}

	// Verify that composite RTT is ascending
	for i := 1; i < len(chains); i++ {
		if chains[i].EstimatedRTT < chains[i-1].EstimatedRTT {
			t.Errorf("chains not sorted by latency: [%d] %v < [%d] %v", i, chains[i].EstimatedRTT, i-1, chains[i-1].EstimatedRTT)
		}
	}
}

func Example_buildChains() {
	engine := New(
		WithStrategy(StrategyDomesticRelayInternationalExit),
		WithDomesticCountry("IR"),
		WithMaxLatencyCeiling(400*time.Millisecond),
	)

	pool := []Node{
		{UniqueHash: "h1", Protocol: "vless", Address: "1.1.1.1", Port: 443, CountryCode: "IR", Latency: 20 * time.Millisecond, Alive: true},
		{UniqueHash: "h2", Protocol: "trojan", Address: "2.2.2.2", Port: 443, CountryCode: "DE", Latency: 75 * time.Millisecond, Alive: true},
	}

	chains, _ := engine.Synthesize(context.Background(), pool)
	_ = chains
}
