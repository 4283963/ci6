package feed

import (
	"log"
	"math/rand"
	"sync"
	"time"

	"quant-feed/config"
	"quant-feed/redis"
)

type FeeFeed struct {
	cfg          *config.Config
	redis        *redis.Client
	symbols      []string
	makerFees    map[string]float64
	takerFees    map[string]float64
	fundingRates map[string]float64
	mu           sync.RWMutex
	stopCh       chan struct{}
	rng          *rand.Rand
}

func NewFeeFeed(cfg *config.Config, redisClient *redis.Client) *FeeFeed {
	makerFees := make(map[string]float64)
	takerFees := make(map[string]float64)
	fundingRates := make(map[string]float64)

	for _, symbol := range cfg.Symbols {
		makerFees[symbol] = 0.0002 + rand.Float64()*0.0001
		takerFees[symbol] = 0.0005 + rand.Float64()*0.0002
		fundingRates[symbol] = (rand.Float64() - 0.5) * 0.001
	}

	return &FeeFeed{
		cfg:          cfg,
		redis:        redisClient,
		symbols:      cfg.Symbols,
		makerFees:    makerFees,
		takerFees:    takerFees,
		fundingRates: fundingRates,
		stopCh:       make(chan struct{}),
		rng:          rand.New(rand.NewSource(time.Now().UnixNano())),
	}
}

func (f *FeeFeed) Start() {
	ticker := time.NewTicker(1 * time.Second)
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

func (f *FeeFeed) Stop() {
	close(f.stopCh)
}

func (f *FeeFeed) tick() {
	f.mu.Lock()
	defer f.mu.Unlock()

	for _, symbol := range f.symbols {
		f.fundingRates[symbol] += (f.rng.Float64() - 0.5) * 0.00005
		if f.fundingRates[symbol] > 0.005 {
			f.fundingRates[symbol] = 0.005
		}
		if f.fundingRates[symbol] < -0.005 {
			f.fundingRates[symbol] = -0.005
		}

		f.makerFees[symbol] = 0.0002 + f.rng.Float64()*0.0001
		f.takerFees[symbol] = 0.0005 + f.rng.Float64()*0.0002
	}
}

func (f *FeeFeed) PushSnapshot() {
	f.mu.RLock()
	defer f.mu.RUnlock()

	now := time.Now().UnixNano() / int64(time.Millisecond)

	for _, symbol := range f.symbols {
		data := redis.FeeData{
			Symbol:      symbol,
			MakerFee:    f.makerFees[symbol],
			TakerFee:    f.takerFees[symbol],
			FundingRate: f.fundingRates[symbol],
			Timestamp:   now,
		}

		if err := f.redis.PublishFeeData(data); err != nil {
			log.Printf("Failed to publish fee data for %s: %v", symbol, err)
		}
	}
}

func (f *FeeFeed) GetFeeData(symbol string) (maker, taker, funding float64) {
	f.mu.RLock()
	defer f.mu.RUnlock()
	return f.makerFees[symbol], f.takerFees[symbol], f.fundingRates[symbol]
}
