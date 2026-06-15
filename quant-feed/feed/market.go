package feed

import (
	"log"
	"math/rand"
	"sync"
	"time"

	"quant-feed/config"
	"quant-feed/redis"
)

type MarketFeed struct {
	cfg     *config.Config
	redis   *redis.Client
	symbols []string
	prices  map[string]float64
	volumes map[string]float64
	high24h map[string]float64
	low24h  map[string]float64
	open24h map[string]float64
	mu      sync.RWMutex
	stopCh  chan struct{}
	rng     *rand.Rand
}

func NewMarketFeed(cfg *config.Config, redisClient *redis.Client) *MarketFeed {
	prices := make(map[string]float64)
	volumes := make(map[string]float64)
	high24h := make(map[string]float64)
	low24h := make(map[string]float64)
	open24h := make(map[string]float64)

	basePrices := map[string]float64{
		"BTC": 67000, "ETH": 3500, "SOL": 150, "BNB": 580, "XRP": 0.52,
		"ADA": 0.45, "DOGE": 0.12, "DOT": 7.2, "AVAX": 35, "LINK": 14.5,
	}

	for _, symbol := range cfg.Symbols {
		price := basePrices[symbol]
		prices[symbol] = price
		open24h[symbol] = price * (1 + (rand.Float64()-0.5)*0.05)
		high24h[symbol] = price * 1.03
		low24h[symbol] = price * 0.97
		volumes[symbol] = price * 1000000 * rand.Float64()
	}

	return &MarketFeed{
		cfg:     cfg,
		redis:   redisClient,
		symbols: cfg.Symbols,
		prices:  prices,
		volumes: volumes,
		high24h: high24h,
		low24h:  low24h,
		open24h: open24h,
		stopCh:  make(chan struct{}),
		rng:     rand.New(rand.NewSource(time.Now().UnixNano())),
	}
}

func (f *MarketFeed) Start() {
	ticker := time.NewTicker(50 * time.Millisecond)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			f.tick()
		case <-f.stopCh:
			return
		}
	}
}

func (f *MarketFeed) Stop() {
	close(f.stopCh)
}

func (f *MarketFeed) tick() {
	f.mu.Lock()
	defer f.mu.Unlock()

	for _, symbol := range f.symbols {
		change := (f.rng.Float64() - 0.5) * 0.002
		newPrice := f.prices[symbol] * (1 + change)
		f.prices[symbol] = newPrice

		if newPrice > f.high24h[symbol] {
			f.high24h[symbol] = newPrice
		}
		if newPrice < f.low24h[symbol] {
			f.low24h[symbol] = newPrice
		}

		f.volumes[symbol] += f.rng.Float64() * f.prices[symbol] * 100
	}
}

func (f *MarketFeed) PushSnapshot() {
	f.mu.RLock()
	defer f.mu.RUnlock()

	now := time.Now().UnixNano() / int64(time.Millisecond)

	for _, symbol := range f.symbols {
		price := f.prices[symbol]
		change24h := (price - f.open24h[symbol]) / f.open24h[symbol] * 100

		data := redis.MarketData{
			Symbol:    symbol,
			Price:     price,
			Volume:    f.volumes[symbol],
			Timestamp: now,
			High24h:   f.high24h[symbol],
			Low24h:    f.low24h[symbol],
			Change24h: change24h,
		}

		if err := f.redis.PublishMarketData(data); err != nil {
			log.Printf("Failed to publish market data for %s: %v", symbol, err)
		}
	}
}

func (f *MarketFeed) GetPrice(symbol string) float64 {
	f.mu.RLock()
	defer f.mu.RUnlock()
	return f.prices[symbol]
}

func (f *MarketFeed) GetAllPrices() map[string]float64 {
	f.mu.RLock()
	defer f.mu.RUnlock()
	prices := make(map[string]float64)
	for k, v := range f.prices {
		prices[k] = v
	}
	return prices
}
