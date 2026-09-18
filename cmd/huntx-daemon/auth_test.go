package main

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func newAuthTestHandler(t *testing.T, token string) http.Handler {
	t.Helper()
	t.Setenv("HUNTX_DAEMON_CONTROL_TOKEN", token)
	return NewDaemon([]DaemonNode{
		{ID: "a", Protocol: "http", Server: "1.1.1.1", Port: 443, Alive: true},
		{ID: "b", Protocol: "http", Server: "8.8.8.8", Port: 443, Alive: true},
	}).Handler()
}

func rotateWith(handler http.Handler, authorization string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(http.MethodPost, "/rotate", nil)
	if authorization != "" {
		req.Header.Set("Authorization", authorization)
	}
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)
	return rr
}

func TestRotateRejectsEveryMalformedCredential(t *testing.T) {
	handler := newAuthTestHandler(t, "s3cret")
	cases := map[string]string{
		"missing header":          "",
		"wrong token":             "Bearer nope",
		"prefix of the token":     "Bearer s3cre",
		"token with extra suffix": "Bearer s3cretX",
		"wrong scheme":            "Basic s3cret",
		"lowercase scheme":        "bearer s3cret",
		"no scheme":               "s3cret",
		"scheme only":             "Bearer ",
		"empty bearer":            "Bearer",
	}
	for name, header := range cases {
		t.Run(name, func(t *testing.T) {
			rr := rotateWith(handler, header)
			if rr.Code != http.StatusUnauthorized {
				t.Fatalf("Authorization %q: expected 401, got %d", header, rr.Code)
			}
		})
	}
}

func TestRotateAcceptsTheConfiguredToken(t *testing.T) {
	handler := newAuthTestHandler(t, "s3cret")
	if rr := rotateWith(handler, "Bearer s3cret"); rr.Code != http.StatusOK {
		t.Fatalf("expected 200 for the correct token, got %d", rr.Code)
	}
}

func TestRotateIsDisabledWhenNoTokenIsConfigured(t *testing.T) {
	handler := newAuthTestHandler(t, "")
	// An empty configured token must never match an empty or bare credential.
	for _, header := range []string{"", "Bearer ", "Bearer"} {
		if rr := rotateWith(handler, header); rr.Code != http.StatusUnauthorized {
			t.Fatalf("Authorization %q with no token configured: expected 401, got %d", header, rr.Code)
		}
	}
}

func TestRotateChallengesAndForbidsCaching(t *testing.T) {
	handler := newAuthTestHandler(t, "s3cret")
	rr := rotateWith(handler, "Bearer wrong")
	if got := rr.Header().Get("WWW-Authenticate"); got == "" {
		t.Error("a 401 must carry a WWW-Authenticate challenge (RFC 9110 section 11.6.1)")
	}
	if got := rr.Header().Get("Cache-Control"); got != "no-store" {
		t.Errorf("Cache-Control = %q, want no-store", got)
	}
}

func TestReadEndpointsForbidCaching(t *testing.T) {
	handler := newAuthTestHandler(t, "s3cret")
	for _, path := range []string{"/status", "/proxy.pac"} {
		rr := httptest.NewRecorder()
		handler.ServeHTTP(rr, httptest.NewRequest(http.MethodGet, path, nil))
		if rr.Code != http.StatusOK {
			t.Fatalf("%s: expected 200, got %d", path, rr.Code)
		}
		if got := rr.Header().Get("Cache-Control"); got != "no-store" {
			t.Errorf("%s: Cache-Control = %q, want no-store", path, got)
		}
		if got := rr.Header().Get("X-Content-Type-Options"); got != "nosniff" {
			t.Errorf("%s: X-Content-Type-Options = %q, want nosniff", path, got)
		}
	}
}

func TestRotateRejectsNonPost(t *testing.T) {
	handler := newAuthTestHandler(t, "s3cret")
	req := httptest.NewRequest(http.MethodGet, "/rotate", nil)
	req.Header.Set("Authorization", "Bearer s3cret")
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)
	if rr.Code != http.StatusMethodNotAllowed {
		t.Fatalf("expected 405 for GET /rotate, got %d", rr.Code)
	}
}
