package main

import (
	"log"
	"os"
	"os/signal"
	"sync/atomic"
	"syscall"
	"time"

	"quant-feed/config"
	"quant-feed/feed"
	"quant-feed/redis"
	"quant-feed/websocket"
)

type BackpressureController struct {
	cfg                   *config.Config
	currentIntervalMs     atomic.Int64
	lastBackpressureCheck time.Time
}

func NewBackpressureController(cfg *config.Config) *BackpressureController {
	bc := &BackpressureController{cfg: cfg}
	bc.currentIntervalMs.Store(int64(cfg.PushIntervalMs))
	return bc
}

func (bc *BackpressureController) GetInterval() time.Duration {
	return time.Duration(bc.currentIntervalMs.Load()) * time.Millisecond
}

func (bc *BackpressureController) Adjust(status redis.BackpressureStatus) {
	if !bc.cfg.EnableBackpressure {
		return
	}

	now := time.Now()
	if now.Sub(bc.lastBackpressureCheck) < 2*time.Second {
		return
	}
	bc.lastBackpressureCheck = now

	current := bc.currentIntervalMs.Load()
	var newInterval int64

	switch {
	case status.HealthStatus == "critical":
		newInterval = int64(bc.cfg.MaxPushIntervalMs)
		log.Printf("BACKPRESSURE [CRITICAL]: consumer lag=%dms, drop_rate=%.2f%%, slowing to %dms",
			status.ConsumerLagMs, status.DropRate*100, newInterval)

	case status.HealthStatus == "degraded" || status.ConsumerStale:
		newInterval = current * 2
		if newInterval > int64(bc.cfg.MaxPushIntervalMs) {
			newInterval = int64(bc.cfg.MaxPushIntervalMs)
		}
		log.Printf("BACKPRESSURE [DEGRADED]: consumer lag=%dms, drop_rate=%.2f%%, adjusting interval %dms -> %dms",
			status.ConsumerLagMs, status.DropRate*100, current, newInterval)

	case status.HealthStatus == "healthy" && status.ConsumerLagMs < 500 && status.DropRate < 0.01:
		newInterval = current * 4 / 5
		if newInterval < int64(bc.cfg.MinPushIntervalMs) {
			newInterval = int64(bc.cfg.MinPushIntervalMs)
		}
		if newInterval != current {
			log.Printf("BACKPRESSURE [RECOVERY]: consumer lag=%dms, speeding up interval %dms -> %dms",
				status.ConsumerLagMs, current, newInterval)
		}

	default:
		newInterval = current
	}

	if newInterval != current {
		bc.currentIntervalMs.Store(newInterval)
	}
}

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

	backpressure := NewBackpressureController(cfg)

	ticker := time.NewTicker(backpressure.GetInterval())
	defer ticker.Stop()

	backpressureTicker := time.NewTicker(3 * time.Second)
	defer backpressureTicker.Stop()

	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	log.Printf("quant-feed started with push_interval=%dms, backpressure=%v",
		cfg.PushIntervalMs, cfg.EnableBackpressure)

	for {
		select {
		case <-ticker.C:
			marketFeed.PushSnapshot()
			feeFeed.PushSnapshot()

		case <-backpressureTicker.C:
			status := redisClient.CheckConsumerBackpressure()
			backpressure.Adjust(status)

			newInterval := backpressure.GetInterval()
			ticker.Reset(newInterval)

			_ = redisClient.SetFeedHealth(
				status.HealthStatus,
				status.ConsumerLagMs,
				int(newInterval/time.Millisecond),
			)

		case <-sigChan:
			log.Println("Shutting down quant-feed...")
			marketFeed.Stop()
			feeFeed.Stop()
			wsServer.Stop()
			return
		}
	}
}
