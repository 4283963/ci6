package config

import (
	"os"
	"strconv"
)

type Config struct {
	Redis          RedisConfig
	PushIntervalMs int
	Symbols        []string
	WebSocketPort  string
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
		PushIntervalMs: getEnvInt("PUSH_INTERVAL_MS", 100),
		Symbols: []string{
			"BTC", "ETH", "SOL", "BNB", "XRP",
			"ADA", "DOGE", "DOT", "AVAX", "LINK",
		},
		WebSocketPort: getEnv("WS_PORT", ":8080"),
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
