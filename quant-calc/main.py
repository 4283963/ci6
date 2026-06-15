import json
import time
import threading
import logging
import signal
import sys
from typing import Dict, Optional
import redis
import numpy as np

from config import load_config
from data_manager import DataManager
from risk_calculator import RiskCalculator, PortfolioRiskCalculator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("quant-calc")


class ThreadSupervisor:
    def __init__(self, check_interval: float = 5.0):
        self._threads: Dict[str, threading.Thread] = {}
        self._last_heartbeat: Dict[str, float] = {}
        self._targets: Dict[str, callable] = {}
        self._lock = threading.Lock()
        self.check_interval = check_interval
        self.running = False

    def register(self, name: str, target: callable, daemon: bool = True):
        with self._lock:
            self._targets[name] = target
            self._threads[name] = self._create_thread(name, target, daemon)
            self._last_heartbeat[name] = time.time()
            logger.info(f"Registered thread: {name}")

    def _create_thread(self, name: str, target: callable, daemon: bool) -> threading.Thread:
        def wrapped():
            logger.info(f"Thread '{name}' starting")
            consecutive_failures = 0
            while self.running:
                try:
                    self._last_heartbeat[name] = time.time()
                    target()
                    consecutive_failures = 0
                except Exception as e:
                    consecutive_failures += 1
                    backoff = min(2 ** consecutive_failures, 30)
                    logger.error(
                        f"Thread '{name}' crashed (failure #{consecutive_failures}): {e}",
                        exc_info=True
                    )
                    self._last_heartbeat[name] = time.time()
                    time.sleep(backoff)
            logger.info(f"Thread '{name}' exited gracefully")

        t = threading.Thread(target=wrapped, name=name, daemon=daemon)
        return t

    def heartbeat(self, name: str):
        with self._lock:
            self._last_heartbeat[name] = time.time()

    def _is_thread_alive(self, name: str) -> bool:
        thread = self._threads.get(name)
        return thread is not None and thread.is_alive()

    def _check_and_restart(self):
        with self._lock:
            now = time.time()
            for name, thread in list(self._threads.items()):
                target = self._targets.get(name)
                last_hb = self._last_heartbeat.get(name, 0)
                stale_threshold = self.check_interval * 6

                if not thread.is_alive():
                    logger.warning(f"Thread '{name}' is dead, restarting...")
                    self._threads[name] = self._create_thread(name, target, True)
                    self._threads[name].start()
                elif now - last_hb > stale_threshold:
                    logger.warning(
                        f"Thread '{name}' heartbeat stale "
                        f"({now - last_hb:.1f}s > {stale_threshold:.1f}s), "
                        f"may be stuck"
                    )

    def start_all(self):
        self.running = True
        with self._lock:
            for name, thread in self._threads.items():
                if not thread.is_alive():
                    thread.start()
        logger.info("All threads started")

        monitor_thread = threading.Thread(
            target=self._monitor_loop,
            name="thread-supervisor",
            daemon=True
        )
        monitor_thread.start()

    def _monitor_loop(self):
        logger.info("Thread supervisor started")
        while self.running:
            try:
                self._check_and_restart()
            except Exception as e:
                logger.error(f"Supervisor check error: {e}", exc_info=True)
            time.sleep(self.check_interval)

    def stop_all(self):
        self.running = False
        logger.info("Thread supervisor stopping all threads")


class QuantCalcEngine:
    def __init__(self):
        self.config = load_config()
        self.running = False

        self.redis_client = redis.Redis(
            host=self.config.redis_host,
            port=self.config.redis_port,
            db=self.config.redis_db,
            password=self.config.redis_password or None,
            decode_responses=True,
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
            retry_on_timeout=True
        )

        self.data_manager = DataManager(
            self.redis_client,
            self.config.symbols,
            self.config.lookback_window
        )

        self.risk_calculator = RiskCalculator(
            risk_free_rate=self.config.risk_free_rate,
            confidence_level=self.config.confidence_level
        )

        self.portfolio_calculator = PortfolioRiskCalculator(self.risk_calculator)

        self._risk_cache: Dict[str, dict] = {}
        self._covariance_matrix: np.ndarray = np.array([])
        self._correlation_matrix: np.ndarray = np.array([])
        self._cache_lock = threading.Lock()

        self._supervisor = ThreadSupervisor(check_interval=5.0)
        self._last_successful_calc = 0.0

    def start(self):
        logger.info("=" * 60)
        logger.info("Starting quant-calc engine")
        logger.info(f"Symbols: {self.config.symbols}")
        logger.info(f"Lookback window: {self.config.lookback_window}")
        logger.info(f"Calc interval: {self.config.calc_interval}s")
        logger.info("=" * 60)

        self.running = True

        self._supervisor.register("market-listener", self._market_listener)
        self._supervisor.register("fee-listener", self._fee_listener)
        self._supervisor.register("calculation-loop", self._calculation_loop)
        self._supervisor.register("health-publisher", self._health_publisher)

        self._supervisor.start_all()

        logger.info("quant-calc engine started successfully")

        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._signal_handler)

        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

        self.stop()

    def _signal_handler(self, signum, frame):
        logger.info(f"Received signal {signum}, initiating shutdown")
        self.stop()

    def stop(self):
        if not self.running:
            return
        self.running = False
        self._supervisor.stop_all()
        try:
            self.redis_client.close()
        except Exception:
            pass
        logger.info("quant-calc engine stopped")

    def _market_listener(self):
        logger.info("Starting market data listener...")
        pubsub = None
        try:
            pubsub = self.data_manager.subscribe_market_data()

            for message in pubsub.listen():
                if not self.running:
                    break

                self._supervisor.heartbeat("market-listener")
                try:
                    symbol = self.data_manager.process_market_message(message)
                    if symbol:
                        logger.debug(f"Received market data for {symbol}")
                except Exception as e:
                    logger.warning(f"Error processing market message: {e}")

        except redis.ConnectionError as e:
            logger.error(f"Redis connection lost in market listener: {e}")
            raise
        finally:
            if pubsub:
                try:
                    pubsub.close()
                except Exception:
                    pass
        logger.info("Market data listener stopped")

    def _fee_listener(self):
        logger.info("Starting fee data listener...")
        pubsub = None
        try:
            pubsub = self.data_manager.subscribe_fee_data()

            for message in pubsub.listen():
                if not self.running:
                    break

                self._supervisor.heartbeat("fee-listener")
                try:
                    self.data_manager.process_fee_message(message)
                except Exception as e:
                    logger.warning(f"Error processing fee message: {e}")

        except redis.ConnectionError as e:
            logger.error(f"Redis connection lost in fee listener: {e}")
            raise
        finally:
            if pubsub:
                try:
                    pubsub.close()
                except Exception:
                    pass
        logger.info("Fee data listener stopped")

    def _calculation_loop(self):
        logger.info("Starting calculation loop...")
        last_cov_calc_time = 0.0
        cov_calc_interval = 1.0
        calc_timeout = 5.0

        while self.running:
            self._supervisor.heartbeat("calculation-loop")
            cycle_start = time.time()

            try:
                if not self.data_manager.all_symbols_ready(min_points=10):
                    remaining = [
                        s for s in self.config.symbols
                        if not self.data_manager.has_enough_data(s, min_points=10)
                    ]
                    if remaining:
                        logger.debug(
                            f"Waiting for data, missing: {remaining}, "
                            f"counts: { {s: self.data_manager.get_data_count(s) for s in remaining} }"
                        )
                    time.sleep(self.config.calc_interval)
                    continue

                self._calculate_individual_risk_factors_safe()

                if time.time() - last_cov_calc_time >= cov_calc_interval:
                    self._calculate_portfolio_metrics_safe()
                    last_cov_calc_time = time.time()

                self._publish_results_safe()
                self._last_successful_calc = time.time()

            except Exception as e:
                logger.error(
                    f"Unhandled error in calculation loop: {e}",
                    exc_info=True
                )

            elapsed = time.time() - cycle_start
            if elapsed > calc_timeout:
                logger.warning(
                    f"Calculation cycle took {elapsed:.2f}s (exceeds {calc_timeout}s) - "
                    f"consider reducing symbols or lookback window"
                )

            sleep_time = max(0, self.config.calc_interval - elapsed)
            time.sleep(sleep_time)

        logger.info("Calculation loop stopped")

    def _calculate_individual_risk_factors_safe(self):
        try:
            prices_snapshot = self.data_manager.get_consistency_snapshot()
            market_prices = self.data_manager.get_market_prices()
            fee_data_copy = self.data_manager.get_fee_data_copy()
        except Exception as e:
            logger.error(f"Failed to get data snapshot: {e}")
            return

        results = {}
        for symbol in self.config.symbols:
            try:
                prices = prices_snapshot.get(symbol, np.array([]))
                if len(prices) < 10:
                    continue

                factors = self.risk_calculator.calculate_all_factors(
                    prices,
                    market_prices if len(market_prices) > 0 else None
                )

                fee = fee_data_copy.get(symbol, {})
                if fee:
                    factors["maker_fee"] = fee.get("makerFee", 0)
                    factors["taker_fee"] = fee.get("takerFee", 0)
                    factors["funding_rate"] = fee.get("fundingRate", 0)

                factors["calc_timestamp"] = time.time()
                results[symbol] = factors

            except Exception as e:
                logger.error(
                    f"Failed to calculate risk factors for {symbol}: {e}",
                    exc_info=True
                )
                with self._cache_lock:
                    if symbol in self._risk_cache:
                        cached = self._risk_cache[symbol].copy()
                        cached["stale"] = True
                        results[symbol] = cached

        with self._cache_lock:
            self._risk_cache.update(results)

    def _calculate_portfolio_metrics_safe(self):
        try:
            returns_dict = self.data_manager.get_all_returns()
        except Exception as e:
            logger.error(f"Failed to get returns: {e}")
            return

        try:
            with self._cache_lock:
                self._covariance_matrix = self.portfolio_calculator.calculate_covariance_matrix(
                    returns_dict
                )
                self._correlation_matrix = self.portfolio_calculator.calculate_correlation_matrix(
                    returns_dict
                )

                n = len(self.config.symbols)
                if n > 0 and self._covariance_matrix.size > 0:
                    equal_weights = np.ones(n) / n

                    individual_vols = np.array([
                        self._risk_cache.get(s, {}).get("volatility", 0.01)
                        for s in self.config.symbols
                    ])
                    individual_vols = np.nan_to_num(individual_vols, nan=0.01)

                    try:
                        port_vol = self.portfolio_calculator.calculate_portfolio_volatility(
                            equal_weights,
                            self._covariance_matrix
                        )
                        port_var = self.portfolio_calculator.calculate_portfolio_var(
                            equal_weights,
                            self._covariance_matrix
                        )
                        div_ratio = self.portfolio_calculator.calculate_diversification_ratio(
                            equal_weights,
                            self._covariance_matrix,
                            individual_vols
                        )
                        risk_contrib = self.portfolio_calculator.calculate_risk_contribution(
                            equal_weights,
                            self._covariance_matrix
                        )

                        portfolio_metrics = {
                            "portfolio_volatility": float(port_vol),
                            "portfolio_var_95": float(port_var),
                            "diversification_ratio": float(div_ratio),
                            "risk_contributions": {
                                s: float(rc)
                                for s, rc in zip(self.config.symbols, risk_contrib)
                            },
                            "calc_timestamp": time.time()
                        }

                        self._risk_cache["__portfolio__"] = portfolio_metrics
                    except Exception as e:
                        logger.error(f"Portfolio metrics calculation failed: {e}")

        except Exception as e:
            logger.error(
                f"Fatal error in portfolio calculation: {e}",
                exc_info=True
            )

    def _publish_results_safe(self):
        max_hset_attempts = 3
        for attempt in range(max_hset_attempts):
            try:
                with self._cache_lock:
                    cache_copy = {
                        k: (v.copy() if isinstance(v, dict) else v)
                        for k, v in self._risk_cache.items()
                    }
                    cov_copy = self._covariance_matrix.copy() if self._covariance_matrix.size else np.array([])
                    corr_copy = self._correlation_matrix.copy() if self._correlation_matrix.size else np.array([])

                for symbol, factors in cache_copy.items():
                    if not isinstance(factors, dict):
                        continue
                    try:
                        if symbol == "__portfolio__":
                            key = "risk:portfolio"
                            self.redis_client.hset(
                                key,
                                mapping=self._flatten_dict(factors)
                            )
                        else:
                            key = f"risk:{symbol}"
                            self.redis_client.hset(
                                key,
                                mapping={
                                    k: (str(v) if not isinstance(v, str) else v)
                                    for k, v in factors.items()
                                }
                            )
                    except Exception as e:
                        logger.warning(f"Failed to publish {symbol}: {e}")

                if cov_copy.size > 0:
                    try:
                        cov_data = json.dumps({
                            "symbols": self.config.symbols,
                            "matrix": cov_copy.tolist(),
                            "timestamp": int(time.time() * 1000)
                        })
                        self.redis_client.set("risk:covariance_matrix", cov_data)
                    except Exception as e:
                        logger.warning(f"Failed to publish covariance matrix: {e}")

                if corr_copy.size > 0:
                    try:
                        corr_data = json.dumps({
                            "symbols": self.config.symbols,
                            "matrix": corr_copy.tolist(),
                            "timestamp": int(time.time() * 1000)
                        })
                        self.redis_client.set("risk:correlation_matrix", corr_data)
                    except Exception as e:
                        logger.warning(f"Failed to publish correlation matrix: {e}")

                try:
                    self.redis_client.publish("channel:risk", json.dumps({
                        "type": "risk_update",
                        "timestamp": int(time.time() * 1000),
                        "symbols_updated": [
                            s for s in self.config.symbols if s in cache_copy
                        ]
                    }))
                except Exception as e:
                    logger.warning(f"Failed to publish risk notification: {e}")

                return

            except redis.ConnectionError as e:
                logger.error(
                    f"Redis connection error during publish (attempt {attempt + 1}/{max_hset_attempts}): {e}"
                )
                if attempt < max_hset_attempts - 1:
                    time.sleep(0.5 * (attempt + 1))
            except Exception as e:
                logger.error(f"Unexpected publish error: {e}", exc_info=True)
                return

        logger.error("Failed to publish results after all retries")

    def _health_publisher(self):
        logger.info("Starting health publisher...")
        while self.running:
            self._supervisor.heartbeat("health-publisher")
            try:
                stats = self.data_manager.get_stats()
                now = time.time()
                health = {
                    "status": "healthy" if now - self._last_successful_calc < 10 else "degraded",
                    "last_successful_calc": self._last_successful_calc,
                    "timestamp": now,
                    "symbols_cached": 0,
                    **stats
                }

                with self._cache_lock:
                    health["symbols_cached"] = len(
                        [s for s in self.config.symbols if s in self._risk_cache]
                    )

                try:
                    self.redis_client.set(
                        "quant-calc:health",
                        json.dumps(health),
                        ex=30
                    )
                except Exception as e:
                    logger.debug(f"Failed to publish health: {e}")

            except Exception as e:
                logger.warning(f"Health publisher error: {e}")

            time.sleep(2.0)

    def _flatten_dict(self, d: dict, parent_key: str = "", sep: str = ".") -> dict:
        items = {}
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.update(self._flatten_dict(v, new_key, sep))
            else:
                items[new_key] = str(v) if not isinstance(v, str) else v
        return items


def main():
    engine = QuantCalcEngine()
    engine.start()


if __name__ == "__main__":
    main()
