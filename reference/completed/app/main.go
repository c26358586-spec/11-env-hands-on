/*
Copyright 2026 Ranamicus Technology LLC. All rights reserved.
*/

package main

import (
	"log"
	"net/http"
	"os"
	"time"
)

var version = "dev"

func main() {
	addr := os.Getenv("APP_ADDR")
	if addr == "" {
		addr = "127.0.0.1:8080"
	}

	server := &http.Server{
		Addr:              addr,
		Handler:           routes(),
		ReadHeaderTimeout: 5 * time.Second,
	}

	log.Printf("starting ms1-go-api version=%s addr=%s", version, addr)
	if err := server.ListenAndServe(); err != nil {
		log.Fatal(err)
	}
}
