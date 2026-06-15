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

        self._custom_weights: Dict[str, float] = {}
        self._custom_portfolio_cache: Optional[dict] = None
        self._last_weight_update = 0.0
        self._weight_debounce_interval = 0.1

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
        self._supervisor.register("weight-listener", self._weight_listener)
        self._supervisor.register("portfolio-calc", self._custom_portfolio_calc_loop)

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

    def _weight_listener(self):
        logger.info("Starting weight update listener...")
        pubsub = None
        try:
            pubsub = self.redis_client.pubsub()
            pubsub.subscribe("channel:weights")

            for message in pubsub.listen():
                if not self.running:
                    break

                self._supervisor.heartbeat("weight-listener")
                if message["type"] != "message":
                    continue

                try:
                    data = json.loads(message["data"])
                    weights = data.get("weights", {})
                    if not isinstance(weights, dict) or len(weights) == 0:
                        continue

                    valid_weights = {}
                    for symbol in self.config.symbols:
                        w = weights.get(symbol, 0)
                        if isinstance(w, (int, float)) and w > 0:
                            valid_weights[symbol] = float(w)

                    if len(valid_weights) == 0:
                        continue

                    total = sum(valid_weights.values())
                    if total <= 0:
                        continue

                    normalized = {s: w / total for s, w in valid_weights.items()}

                    with self._cache_lock:
                        self._custom_weights = normalized
                        self._last_weight_update = time.time()

                    logger.debug(
                        f"Received custom weights: {len(valid_weights)} symbols, "
                        f"top 3: {sorted(normalized.items(), key=lambda x: -x[1])[:3]}"
                    )

                except (json.JSONDecodeError, ValueError, TypeError) as e:
                    logger.warning(f"Failed to parse weight message: {e}")

        except redis.ConnectionError as e:
            logger.error(f"Redis connection lost in weight listener: {e}")
            raise
        finally:
            if pubsub:
                try:
                    pubsub.close()
                except Exception:
                    pass
        logger.info("Weight update listener stopped")

    def _custom_portfolio_calc_loop(self):
        logger.info("Starting custom portfolio calculation loop...")
        last_calc_time = 0
        min_calc_interval = 0.05

        while self.running:
            self._supervisor.heartbeat("portfolio-calc")

            try:
                now = time.time()

                with self._cache_lock:
                    weights = self._custom_weights.copy()
                    last_weight_ts = self._last_weight_update

                if not weights or len(weights) == 0:
                    time.sleep(0.1)
                    continue

                if now - last_calc_time < min_calc_interval:
                    time.sleep(min_calc_interval - (now - last_calc_time))
                    continue

                with self._cache_lock:
                    cov_matrix = self._covariance_matrix.copy() if self._covariance_matrix.size > 0 else np.array([])

                prices_snapshot = self.data_manager.get_consistency_snapshot()
                returns_dict = {}
                for s in self.config.symbols:
                    prices = prices_snapshot.get(s, np.array([]))
                    if len(prices) >= 2:
                        returns = np.diff(prices) / prices[:-1]
                        returns = np.nan_to_num(returns, nan=0.0, posinf=0.0, neginf=0.0)
                        returns_dict[s] = returns

                if len(returns_dict) < 2:
                    time.sleep(0.1)
                    continue

                valid_symbols = [s for s in self.config.symbols if s in weights and s in returns_dict]
                if len(valid_symbols) < 2:
                    time.sleep(0.1)
                    continue

                weight_array = np.array([weights[s] for s in valid_symbols])
                weight_sum = weight_array.sum()
                if weight_sum <= 0:
                    time.sleep(0.1)
                    continue
                weight_array = weight_array / weight_sum

                returns_array = [returns_dict[s] for s in valid_symbols]
                min_len = min(len(r) for r in returns_array)
                if min_len < 5:
                    time.sleep(0.1)
                    continue

                aligned_returns = np.array([r[-min_len:] for r in returns_array])
                annualization = 365 * 24 * 60 * 60 / 5

                individual_returns = np.array([
                    self.risk_calculator._calculate_annual_return(prices_snapshot.get(s, np.array([])))
                    if len(prices_snapshot.get(s, np.array([]))) >= 2 else 0.0
                    for s in valid_symbols
                ])

                individual_vols = np.array([
                    np.std(returns_dict[s], ddof=1) * np.sqrt(annualization)
                    if len(returns_dict[s]) >= 2 else 0.01
                    for s in valid_symbols
                ])
                individual_vols = np.nan_to_num(individual_vols, nan=0.01)

                expected_return = float(np.dot(weight_array, individual_returns))

                portfolio_vol = 0.0
                if cov_matrix.size > 0 and cov_matrix.shape == (len(self.config.symbols), len(self.config.symbols)):
                    indices = [self.config.symbols.index(s) for s in valid_symbols]
                    sub_cov = cov_matrix[np.ix_(indices, indices)]
                    try:
                        portfolio_vol = float(np.sqrt(max(0, weight_array @ sub_cov @ weight_array.T)))
                    except Exception:
                        portfolio_vol = float(np.dot(weight_array, individual_vols))
                else:
                    try:
                        sample_cov = np.cov(aligned_returns, ddof=1)
                        annualized_cov = sample_cov * annualization
                        portfolio_vol = float(np.sqrt(max(0, weight_array @ annualized_cov @ weight_array.T)))
                    except Exception:
                        portfolio_vol = float(np.dot(weight_array, individual_vols))

                sharpe_ratio = expected_return / portfolio_vol if portfolio_vol > 0 else 0.0

                var95 = portfolio_vol * 1.645
                cvar95 = portfolio_vol * 2.06

                risk_contributions = {}
                total_risk = 0.0
                for i, s in enumerate(valid_symbols):
                    contrib = weight_array[i] * individual_vols[i]
                    risk_contributions[s] = float(contrib)
                    total_risk += contrib
                if total_risk > 0:
                    risk_contributions = {s: c / total_risk for s, c in risk_contributions.items()}

                avg_correlation = 0.0
                if len(valid_symbols) > 1:
                    try:
                        corr_matrix = np.corrcoef(aligned_returns)
                        n = len(valid_symbols)
                        off_diag_sum = np.sum(corr_matrix) - np.trace(corr_matrix)
                        avg_correlation = float(off_diag_sum / (n * (n - 1)))
                    except Exception:
                        avg_correlation = 0.5

                weighted_avg_vol = float(np.dot(weight_array, individual_vols))
                diversification_ratio = weighted_avg_vol / portfolio_vol if portfolio_vol > 0 else 1.0

                _, max_dd, _ = self._calc_portfolio_drawdown(
                    prices_snapshot, weights, valid_symbols
                )

                sortino_ratio = self._calc_portfolio_sortino(
                    returns_dict, weights, valid_symbols, expected_return
                )

                calmar_ratio = expected_return / abs(max_dd) if max_dd < 0 else 0.0

                var_decomposition = {}
                if cov_matrix.size > 0 and cov_matrix.shape == (len(self.config.symbols), len(self.config.symbols)):
                    indices = [self.config.symbols.index(s) for s in valid_symbols]
                    sub_cov = cov_matrix[np.ix_(indices, indices)]
                    if portfolio_vol > 0:
                        mrc = sub_cov @ weight_array / portfolio_vol
                        rc = weight_array * mrc
                        total_rc = np.sum(rc)
                        if total_rc > 0:
                            for i, s in enumerate(valid_symbols):
                                var_decomposition[s] = float(rc[i] / total_rc)

                portfolio_result = {
                    "weights": {s: float(w) for s, w in weights.items()},
                    "expected_return": round(expected_return, 6),
                    "portfolio_volatility": round(portfolio_vol, 6),
                    "sharpe_ratio": round(sharpe_ratio, 4),
                    "sortino_ratio": round(sortino_ratio, 4),
                    "calmar_ratio": round(calmar_ratio, 4),
                    "max_drawdown": round(max_dd, 6),
                    "var_95": round(var95, 6),
                    "cvar_95": round(cvar95, 6),
                    "diversification_ratio": round(diversification_ratio, 4),
                    "avg_correlation": round(avg_correlation, 4),
                    "risk_contributions": {s: round(v, 6) for s, v in risk_contributions.items()},
                    "variance_decomposition": {s: round(v, 6) for s, v in var_decomposition.items()},
                    "individual_returns": {s: round(float(individual_returns[i]), 6) for i, s in enumerate(valid_symbols)},
                    "individual_vols": {s: round(float(individual_vols[i]), 6) for i, s in enumerate(valid_symbols)},
                    "timestamp": time.time(),
                    "num_assets": len(valid_symbols)
                }

                with self._cache_lock:
                    self._custom_portfolio_cache = portfolio_result

                try:
                    self.redis_client.set(
                        "risk:portfolio_custom",
                        json.dumps(portfolio_result),
                        ex=60
                    )

                    self.redis_client.publish(
                        "channel:portfolio_update",
                        json.dumps({
                            "type": "portfolio_update",
                            "data": portfolio_result,
                            "timestamp": int(time.time() * 1000)
                        })
                    )
                except Exception as e:
                    logger.warning(f"Failed to publish custom portfolio result: {e}")

                last_calc_time = time.time()

            except Exception as e:
                logger.error(
                    f"Error in custom portfolio calculation: {e}",
                    exc_info=True
                )
                time.sleep(0.5)

            time.sleep(0.02)

        logger.info("Custom portfolio calculation loop stopped")

    def _calc_portfolio_drawdown(self, prices_snapshot, weights, valid_symbols):
        try:
            price_arrays = []
            weight_values = []

            for s in valid_symbols:
                prices = prices_snapshot.get(s, np.array([]))
                if len(prices) >= 2:
                    price_arrays.append(prices)
                    weight_values.append(weights.get(s, 0))

            if len(price_arrays) < 2:
                return 0.0, 0.0, 0.0

            min_len = min(len(p) for p in price_arrays)
            aligned = np.array([p[-min_len:] for p in price_arrays])
            weights_arr = np.array(weight_values)
            weights_arr = weights_arr / weights_arr.sum()

            portfolio_values = weights_arr @ aligned
            portfolio_values = portfolio_values / portfolio_values[0]

            peak = np.maximum.accumulate(portfolio_values)
            drawdown = (portfolio_values - peak) / peak
            max_dd = float(np.min(drawdown))

            peak_idx = int(np.argmax(peak))
            trough_idx = int(np.argmin(drawdown[peak_idx:]) + peak_idx)
            recovery_factor = (
                float((portfolio_values[-1] - portfolio_values[trough_idx]) /
                      (portfolio_values[peak_idx] - portfolio_values[trough_idx]))
                if portfolio_values[peak_idx] != portfolio_values[trough_idx]
                else 0.0
            )

            return recovery_factor, max_dd, trough_idx / len(portfolio_values)

        except Exception as e:
            logger.debug(f"Portfolio drawdown calc error: {e}")
            return 0.0, -0.1, 0.0

    def _calc_portfolio_sortino(self, returns_dict, weights, valid_symbols, expected_return):
        try:
            min_len = min(len(returns_dict[s]) for s in valid_symbols)
            if min_len < 5:
                return 0.0

            aligned_returns = np.array([returns_dict[s][-min_len:] for s in valid_symbols])
            weight_array = np.array([weights[s] for s in valid_symbols])
            weight_array = weight_array / weight_array.sum()

            portfolio_returns = weight_array @ aligned_returns

            mar = self.config.risk_free_rate / (365 * 24 * 60 * 60 / 5)
            downside = portfolio_returns[portfolio_returns < mar]
            if len(downside) == 0:
                return float('inf') if expected_return > 0 else 0.0

            downside_dev = np.sqrt(np.mean((downside - mar) ** 2))
            if downside_dev == 0:
                return 0.0

            annualized_downside = downside_dev * np.sqrt(365 * 24 * 60 * 60 / 5)
            return float(expected_return / annualized_downside) if annualized_downside > 0 else 0.0

        except Exception as e:
            logger.debug(f"Portfolio sortino calc error: {e}")
            return 0.0


def main():
    engine = QuantCalcEngine()
    engine.start()


if __name__ == "__main__":
    main()
