package main

import (
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
)

func main() {
	sampleNodes := []DaemonNode{
		{ID: "def-01", Protocol: "vless", Server: "127.0.0.1", Port: 7890, Alive: true, Latency: 35 * time.Millisecond},
	}
	daemon := NewDaemon(sampleNodes)
	server := &http.Server{
		Addr:    ":9090",
		Handler: daemon.Handler(),
	}

	go func() {
		fmt.Printf("[HUNTX-DAEMON] Control API active on http://127.0.0.1:9090\n")
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			fmt.Fprintf(os.Stderr, "server error: %v\n", err)
		}
	}()

	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)
	<-sigChan

	fmt.Println("[HUNTX-DAEMON] Shutting down gracefully...")
}
