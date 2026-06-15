package config

import (
	"os"
	"strconv"
)

type Config struct {
	Redis              RedisConfig
	PushIntervalMs     int
	MinPushIntervalMs  int
	MaxPushIntervalMs  int
	Symbols            []string
	WebSocketPort      string
	EnableBackpressure bool
}

type RedisConfig struct {
	Addr     string
	Password string
	DB       int
}

func Load() (*Config, error) {
	return &Config{
		Redis: RedisConfig{
			Addr:     getEnv("REDIS_ADDR", "localhost:6379"),
			Password: getEnv("REDIS_PASSWORD", ""),
			DB:       getEnvInt("REDIS_DB", 0),
		},
		PushIntervalMs:    getEnvInt("PUSH_INTERVAL_MS", 100),
		MinPushIntervalMs: getEnvInt("MIN_PUSH_INTERVAL_MS", 50),
		MaxPushIntervalMs: getEnvInt("MAX_PUSH_INTERVAL_MS", 500),
		Symbols: []string{
			"BTC", "ETH", "SOL", "BNB", "XRP",
			"ADA", "DOGE", "DOT", "AVAX", "LINK",
		},
		WebSocketPort:      getEnv("WS_PORT", ":8080"),
		EnableBackpressure: getEnvBool("ENABLE_BACKPRESSURE", true),
	}, nil
}

func getEnv(key, defaultValue string) string {
	if value, exists := os.LookupEnv(key); exists {
		return value
	}
	return defaultValue
}

func getEnvInt(key string, defaultValue int) int {
	if value, exists := os.LookupEnv(key); exists {
		if intValue, err := strconv.Atoi(value); err == nil {
			return intValue
		}
	}
	return defaultValue
}

func getEnvBool(key string, defaultValue bool) bool {
	if value, exists := os.LookupEnv(key); exists {
		if boolValue, err := strconv.ParseBool(value); err == nil {
			return boolValue
		}
	}
	return defaultValue
}
