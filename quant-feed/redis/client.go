package redis

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"time"

	"quant-feed/config"

	goredis "github.com/go-redis/redis/v8"
)

type Client struct {
	client *goredis.Client
	ctx    context.Context
}

type MarketData struct {
	Symbol    string  `json:"symbol"`
	Price     float64 `json:"price"`
	Volume    float64 `json:"volume"`
	Timestamp int64   `json:"timestamp"`
	High24h   float64 `json:"high24h"`
	Low24h    float64 `json:"low24h"`
	Change24h float64 `json:"change24h"`
}

type FeeData struct {
	Symbol      string  `json:"symbol"`
	MakerFee    float64 `json:"makerFee"`
	TakerFee    float64 `json:"takerFee"`
	FundingRate float64 `json:"fundingRate"`
	Timestamp   int64   `json:"timestamp"`
}

func NewClient(cfg config.RedisConfig) *Client {
	rdb := goredis.NewClient(&goredis.Options{
		Addr:     cfg.Addr,
		Password: cfg.Password,
		DB:       cfg.DB,
	})

	return &Client{
		client: rdb,
		ctx:    context.Background(),
	}
}

func (c *Client) Ping() error {
	return c.client.Ping(c.ctx).Err()
}

func (c *Client) Close() error {
	return c.client.Close()
}

func (c *Client) PublishMarketData(data MarketData) error {
	key := fmt.Sprintf("market:%s", data.Symbol)
	jsonData, err := json.Marshal(data)
	if err != nil {
		return err
	}

	pipe := c.client.Pipeline()
	pipe.Set(c.ctx, key, jsonData, 0)
	pipe.Publish(c.ctx, "channel:market", jsonData)
	pipe.ZAdd(c.ctx, "market:prices", &goredis.Z{
		Score:  float64(data.Timestamp),
		Member: data.Symbol,
	})
	_, err = pipe.Exec(c.ctx)
	return err
}

func (c *Client) PublishFeeData(data FeeData) error {
	key := fmt.Sprintf("fee:%s", data.Symbol)
	jsonData, err := json.Marshal(data)
	if err != nil {
		return err
	}

	pipe := c.client.Pipeline()
	pipe.Set(c.ctx, key, jsonData, 0)
	pipe.Publish(c.ctx, "channel:fee", jsonData)
	_, err = pipe.Exec(c.ctx)
	return err
}

func (c *Client) GetAllMarketData() ([]MarketData, error) {
	var result []MarketData
	for _, key := range c.client.Keys(c.ctx, "market:*").Val() {
		data, err := c.client.Get(c.ctx, key).Result()
		if err != nil {
			continue
		}
		var md MarketData
		if err := json.Unmarshal([]byte(data), &md); err == nil {
			result = append(result, md)
		}
	}
	return result, nil
}

func (c *Client) Subscribe(channel string) *goredis.PubSub {
	return c.client.Subscribe(c.ctx, channel)
}

func (c *Client) StoreRiskFactors(symbol string, factors map[string]float64) error {
	key := fmt.Sprintf("risk:%s", symbol)
	factors["timestamp"] = float64(time.Now().UnixNano() / int64(time.Millisecond))
	return c.client.HSet(c.ctx, key, factors).Err()
}

func (c *Client) GetRiskFactors(symbol string) (map[string]float64, error) {
	key := fmt.Sprintf("risk:%s", symbol)
	result, err := c.client.HGetAll(c.ctx, key).Result()
	if err != nil {
		return nil, err
	}

	factors := make(map[string]float64)
	for k, v := range result {
		if f, err := parseFloat(v); err == nil {
			factors[k] = f
		}
	}
	return factors, nil
}

func parseFloat(s string) (float64, error) {
	return strconv.ParseFloat(s, 64)
}
