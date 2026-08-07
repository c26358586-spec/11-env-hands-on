/*
Copyright 2026 Ranamicus Technology LLC. All rights reserved.
*/

package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestHealthPayload(t *testing.T) {
	version = "test-version"

	payload := healthPayload()
	if payload.Status != "ok" {
		t.Fatalf("Status = %q, want ok", payload.Status)
	}
	if payload.Service != "ms1-go-api" {
		t.Fatalf("Service = %q, want ms1-go-api", payload.Service)
	}
	if payload.Version != "test-version" {
		t.Fatalf("Version = %q, want test-version", payload.Version)
	}
}

func TestHealthHandler(t *testing.T) {
	version = "test-version"

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	rec := httptest.NewRecorder()
	healthHandler(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status code = %d, want %d", rec.Code, http.StatusOK)
	}

	var got healthResponse
	if err := json.NewDecoder(rec.Body).Decode(&got); err != nil {
		t.Fatalf("decode health response: %v", err)
	}
	if got.Status != "ok" || got.Service != "ms1-go-api" || got.Version != "test-version" {
		t.Fatalf("health response = %+v, want status ok service ms1-go-api version test-version", got)
	}
}
