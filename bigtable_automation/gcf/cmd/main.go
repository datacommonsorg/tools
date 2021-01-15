package main

import (
	"log"
	"os"
	"context"
	"github.com/GoogleCloudPlatform/functions-framework-go/funcframework"
	"btcachegeneration"
)

func main() {
	ctx := context.Background()
	btcachegeneration.CurrentEnv = btcachegeneration.TEST
	if err := funcframework.RegisterEventFunctionContext(ctx, "/", btcachegeneration.BTImportController); err != nil {
		log.Fatalf("funcframework.RegisterEventFunctionContext: %v\n", err)
	}
	// Use PORT environment variable, or default to 8080.
	port := "8080"
	if envPort := os.Getenv("PORT"); envPort != "" {
		port = envPort
	}
	if err := funcframework.Start(port); err != nil {
		log.Fatalf("funcframework.Start: %v\n", err)
	}
}