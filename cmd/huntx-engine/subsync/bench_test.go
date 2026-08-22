package subsync

import (
	"fmt"
	"testing"
)

func BenchmarkDifferThroughput(b *testing.B) {
	differ := NewSubscriptionDiffer()
	baseline := make([]string, 1000)
	incoming := make([]string, 1000)
	for i := 0; i < 1000; i++ {
		baseline[i] = fmt.Sprintf("vless://uuid-%d@server-%d.com:443?type=ws#US-%d", i, i, i)
		if i%5 == 0 {
			incoming[i] = fmt.Sprintf("vless://uuid-%d@server-%d.com:443?type=reality#US-%d-Mutated", i, i, i)
		} else {
			incoming[i] = baseline[i]
		}
	}

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		_ = differ.ComputeDiff(baseline, incoming)
	}
}
