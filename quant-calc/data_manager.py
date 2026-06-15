import json
import numpy as np
from collections import deque
from typing import Dict, Deque, Optional
import redis


class DataManager:
    def __init__(
        self,
        redis_client: redis.Redis,
        symbols: list,
        lookback_window: int = 200
    ):
        self.redis = redis_client
        self.symbols = symbols
        self.lookback_window = lookback_window
        self.price_queues: Dict[str, Deque[float]] = {}
        self.timestamp_queues: Dict[str, Deque[int]] = {}
        self.fee_data: Dict[str, dict] = {}

        for symbol in symbols:
            self.price_queues[symbol] = deque(maxlen=lookback_window)
            self.timestamp_queues[symbol] = deque(maxlen=lookback_window)

    def subscribe_market_data(self) -> redis.client.PubSub:
        pubsub = self.redis.pubsub()
        pubsub.subscribe("channel:market")
        return pubsub

    def subscribe_fee_data(self) -> redis.client.PubSub:
        pubsub = self.redis.pubsub()
        pubsub.subscribe("channel:fee")
        return pubsub

    def process_market_message(self, message: dict) -> Optional[str]:
        if message["type"] != "message":
            return None

        try:
            data = json.loads(message["data"])
            symbol = data.get("symbol")
            if not symbol or symbol not in self.price_queues:
                return None

            price = float(data.get("price", 0))
            timestamp = int(data.get("timestamp", 0))

            self.price_queues[symbol].append(price)
            self.timestamp_queues[symbol].append(timestamp)

            return symbol
        except (json.JSONDecodeError, ValueError, KeyError):
            return None

    def process_fee_message(self, message: dict) -> Optional[str]:
        if message["type"] != "message":
            return None

        try:
            data = json.loads(message["data"])
            symbol = data.get("symbol")
            if not symbol:
                return None

            self.fee_data[symbol] = data
            return symbol
        except (json.JSONDecodeError, KeyError):
            return None

    def get_prices(self, symbol: str) -> np.ndarray:
        return np.array(list(self.price_queues[symbol]))

    def get_all_prices(self) -> Dict[str, np.ndarray]:
        return {symbol: self.get_prices(symbol) for symbol in self.symbols}

    def get_returns(self, symbol: str) -> np.ndarray:
        prices = self.get_prices(symbol)
        if len(prices) < 2:
            return np.array([])
        return np.diff(prices) / prices[:-1]

    def get_all_returns(self) -> Dict[str, np.ndarray]:
        return {symbol: self.get_returns(symbol) for symbol in self.symbols}

    def get_market_prices(self) -> np.ndarray:
        prices_dict = self.get_all_prices()
        if not prices_dict:
            return np.array([])

        min_len = min(len(p) for p in prices_dict.values())
        if min_len == 0:
            return np.array([])

        aligned_prices = []
        for prices in prices_dict.values():
            aligned_prices.append(prices[-min_len:])

        return np.mean(np.array(aligned_prices), axis=0)

    def has_enough_data(self, symbol: str, min_points: int = 10) -> bool:
        return len(self.price_queues[symbol]) >= min_points

    def all_symbols_ready(self, min_points: int = 10) -> bool:
        return all(
            len(self.price_queues[s]) >= min_points
            for s in self.symbols
        )

    def get_data_count(self, symbol: str) -> int:
        return len(self.price_queues[symbol])
