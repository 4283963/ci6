package main

import (
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"quant-feed/config"
	"quant-feed/feed"
	"quant-feed/redis"
	"quant-feed/websocket"
)

func main() {
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	redisClient := redis.NewClient(cfg.Redis)
	defer redisClient.Close()

	if err := redisClient.Ping(); err != nil {
		log.Fatalf("Failed to connect to Redis: %v", err)
	}
	log.Println("Connected to Redis")

	marketFeed := feed.NewMarketFeed(cfg, redisClient)
	feeFeed := feed.NewFeeFeed(cfg, redisClient)

	wsServer := websocket.NewServer(cfg, redisClient)
	go wsServer.Start()

	go marketFeed.Start()
	go feeFeed.Start()

	ticker := time.NewTicker(time.Duration(cfg.PushIntervalMs) * time.Millisecond)
	defer ticker.Stop()

	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	log.Println("quant-feed started successfully")

	for {
		select {
		case <-ticker.C:
			marketFeed.PushSnapshot()
			feeFeed.PushSnapshot()
		case <-sigChan:
			log.Println("Shutting down quant-feed...")
			marketFeed.Stop()
			feeFeed.Stop()
			wsServer.Stop()
			return
		}
	}
}
