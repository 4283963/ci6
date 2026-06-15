import json
import time
import numpy as np
from collections import deque
from threading import Lock
from typing import Dict, Deque, Optional, Tuple
import redis


class DataManager:
    def __init__(
        self,
        redis_client: redis.Redis,
        symbols: list,
        lookback_window: int = 200,
        max_queue_backlog: int = 5000
    ):
        self.redis = redis_client
        self.symbols = symbols
        self.lookback_window = lookback_window
        self.max_queue_backlog = max_queue_backlog

        self._lock = Lock()
        self.price_queues: Dict[str, Deque[float]] = {}
        self.timestamp_queues: Dict[str, Deque[int]] = {}
        self.fee_data: Dict[str, dict] = {}

        self._msg_count = 0
        self._drop_count = 0
        self._last_backpressure_warn = 0.0
        self._backpressure_warn_interval = 5.0

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

            with self._lock:
                self._msg_count += 1

                if len(self.price_queues[symbol]) >= self.max_queue_backlog:
                    self._drop_count += 1
                    now = time.time()
                    if now - self._last_backpressure_warn >= self._backpressure_warn_interval:
                        import logging
                        logging.getLogger("quant-calc").warning(
                            f"Backpressure active for {symbol}: "
                            f"queue={len(self.price_queues[symbol])}, "
                            f"total_dropped={self._drop_count}, "
                            f"total_received={self._msg_count}"
                        )
                        self._last_backpressure_warn = now
                    return None

                self.price_queues[symbol].append(price)
                self.timestamp_queues[symbol].append(timestamp)

            return symbol
        except (json.JSONDecodeError, ValueError, KeyError, TypeError):
            return None

    def process_fee_message(self, message: dict) -> Optional[str]:
        if message["type"] != "message":
            return None

        try:
            data = json.loads(message["data"])
            symbol = data.get("symbol")
            if not symbol:
                return None

            with self._lock:
                self.fee_data[symbol] = data
            return symbol
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    def get_consistency_snapshot(self) -> Dict[str, np.ndarray]:
        with self._lock:
            snapshot = {}
            for symbol in self.symbols:
                snapshot[symbol] = np.array(list(self.price_queues[symbol]), dtype=np.float64)
            return snapshot

    def get_prices(self, symbol: str) -> np.ndarray:
        with self._lock:
            return np.array(list(self.price_queues[symbol]), dtype=np.float64)

    def get_all_prices(self) -> Dict[str, np.ndarray]:
        return self.get_consistency_snapshot()

    def get_returns(self, prices: np.ndarray) -> np.ndarray:
        if len(prices) < 2:
            return np.array([], dtype=np.float64)
        returns = np.diff(prices) / prices[:-1]
        returns = np.nan_to_num(returns, nan=0.0, posinf=0.0, neginf=0.0)
        return returns

    def get_all_returns(self) -> Dict[str, np.ndarray]:
        snapshot = self.get_consistency_snapshot()
        return {
            symbol: self.get_returns(prices)
            for symbol, prices in snapshot.items()
        }

    def get_market_prices(self) -> np.ndarray:
        snapshot = self.get_consistency_snapshot()
        if not snapshot:
            return np.array([], dtype=np.float64)

        valid_prices = [p for p in snapshot.values() if len(p) > 0]
        if not valid_prices:
            return np.array([], dtype=np.float64)

        min_len = min(len(p) for p in valid_prices)
        if min_len == 0:
            return np.array([], dtype=np.float64)

        aligned = [p[-min_len:] for p in valid_prices]
        try:
            stacked = np.vstack(aligned)
            market_prices = np.mean(stacked, axis=0)
            return np.nan_to_num(market_prices, nan=0.0)
        except (ValueError, TypeError):
            return np.array([], dtype=np.float64)

    def has_enough_data(self, symbol: str, min_points: int = 10) -> bool:
        with self._lock:
            return len(self.price_queues.get(symbol, deque())) >= min_points

    def all_symbols_ready(self, min_points: int = 10) -> bool:
        with self._lock:
            return all(
                len(self.price_queues[s]) >= min_points
                for s in self.symbols
                if s in self.price_queues
            )

    def get_data_count(self, symbol: str) -> int:
        with self._lock:
            return len(self.price_queues.get(symbol, deque()))

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "messages_received": self._msg_count,
                "messages_dropped": self._drop_count,
                "drop_rate": (
                    self._drop_count / self._msg_count
                    if self._msg_count > 0
                    else 0.0
                ),
                "queue_sizes": {
                    s: len(self.price_queues[s])
                    for s in self.symbols
                }
            }

    def get_fee_data_copy(self) -> Dict[str, dict]:
        with self._lock:
            return {k: dict(v) for k, v in self.fee_data.items()}
