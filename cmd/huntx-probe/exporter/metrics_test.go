package exporter

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestMetricsExporterAuthHeader(t *testing.T) {
	exp := NewMetricsExporter("secret-auth-token-123")
	handler := exp.Handler()

	// 1. Unauthorized request (no token)
	reqNoAuth := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	recNoAuth := httptest.NewRecorder()
	handler.ServeHTTP(recNoAuth, reqNoAuth)
	if recNoAuth.Code != http.StatusUnauthorized {
		t.Errorf("expected 401 Unauthorized, got %d", recNoAuth.Code)
	}

	// 2. Unauthorized request (wrong token)
	reqBadAuth := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	reqBadAuth.Header.Set("Authorization", "Bearer wrong-token")
	recBadAuth := httptest.NewRecorder()
	handler.ServeHTTP(recBadAuth, reqBadAuth)
	if recBadAuth.Code != http.StatusUnauthorized {
		t.Errorf("expected 401 Unauthorized, got %d", recBadAuth.Code)
	}

	// 3. Authorized request
	reqAuth := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	reqAuth.Header.Set("Authorization", "Bearer secret-auth-token-123")
	recAuth := httptest.NewRecorder()
	handler.ServeHTTP(recAuth, reqAuth)
	if recAuth.Code != http.StatusOK {
		t.Errorf("expected 200 OK, got %d", recAuth.Code)
	}
}

func TestMetricsExporterOutputsPrometheusFormat(t *testing.T) {
	exp := NewMetricsExporter("secret-auth-token-123")
	
	// Record sample probe metrics
	exp.RecordProbeResult("ir-probe-01", "node-vless-1", 35*time.Millisecond, 2.5, 0.0, true)
	exp.RecordProbeResult("ir-probe-01", "node-vless-2", 150*time.Millisecond, 8.0, 0.25, false)

	handler := exp.Handler()
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	req.Header.Set("Authorization", "Bearer secret-auth-token-123")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	body := rec.Body.String()
	if !strings.Contains(body, "# TYPE huntx_probe_latency_seconds gauge") {
		t.Errorf("expected Prometheus gauge definition for latency, got: %s", body)
	}
	if !strings.Contains(body, `huntx_probe_latency_seconds{probe_id="ir-probe-01",target_id="node-vless-1"} 0.035000`) {
		t.Errorf("expected metric line for node-vless-1, got: %s", body)
	}
	if !strings.Contains(body, `huntx_probe_up{probe_id="ir-probe-01",target_id="node-vless-1"} 1`) {
		t.Errorf("expected up metric 1 for node-vless-1, got: %s", body)
	}
	if !strings.Contains(body, `huntx_probe_up{probe_id="ir-probe-01",target_id="node-vless-2"} 0`) {
		t.Errorf("expected up metric 0 for node-vless-2, got: %s", body)
	}
}
