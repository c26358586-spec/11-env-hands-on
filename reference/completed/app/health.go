/*
Copyright 2026 Ranamicus Technology LLC. All rights reserved.
*/

package main

import (
	"encoding/json"
	"net/http"
)

type healthResponse struct {
	Status  string `json:"status"`
	Service string `json:"service"`
	Version string `json:"version"`
}

func routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", healthHandler)
	return mux
}

func healthPayload() healthResponse {
	return healthResponse{
		Status:  "ok",
		Service: "ms1-go-api",
		Version: version,
	}
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	if err := json.NewEncoder(w).Encode(healthPayload()); err != nil {
		http.Error(w, "failed to encode health response", http.StatusInternalServerError)
	}
}
