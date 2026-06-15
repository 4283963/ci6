import json
import time
import threading
import logging
from typing import Dict
import redis
import numpy as np

from config import load_config
from data_manager import DataManager
from risk_calculator import RiskCalculator, PortfolioRiskCalculator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("quant-calc")


class QuantCalcEngine:
    def __init__(self):
        self.config = load_config()
        self.running = False

        self.redis_client = redis.Redis(
            host=self.config.redis_host,
            port=self.config.redis_port,
            db=self.config.redis_db,
            password=self.config.redis_password or None,
            decode_responses=True
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
        self._lock = threading.Lock()

    def start(self):
        logger.info("Starting quant-calc engine...")
        self.running = True

        market_thread = threading.Thread(target=self._market_listener, daemon=True)
        fee_thread = threading.Thread(target=self._fee_listener, daemon=True)
        calc_thread = threading.Thread(target=self._calculation_loop, daemon=True)

        market_thread.start()
        fee_thread.start()
        calc_thread.start()

        logger.info("quant-calc engine started successfully")

        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received interrupt, shutting down...")
            self.stop()

    def stop(self):
        self.running = False
        logger.info("quant-calc engine stopped")

    def _market_listener(self):
        logger.info("Starting market data listener...")
        pubsub = self.data_manager.subscribe_market_data()

        for message in pubsub.listen():
            if not self.running:
                break

            symbol = self.data_manager.process_market_message(message)
            if symbol:
                logger.debug(f"Received market data for {symbol}")

        pubsub.close()
        logger.info("Market data listener stopped")

    def _fee_listener(self):
        logger.info("Starting fee data listener...")
        pubsub = self.data_manager.subscribe_fee_data()

        for message in pubsub.listen():
            if not self.running:
                break

            symbol = self.data_manager.process_fee_message(message)
            if symbol:
                logger.debug(f"Received fee data for {symbol}")

        pubsub.close()
        logger.info("Fee data listener stopped")

    def _calculation_loop(self):
        logger.info("Starting calculation loop...")
        last_cov_calc_time = 0
        cov_calc_interval = 1.0

        while self.running:
            try:
                if not self.data_manager.all_symbols_ready(min_points=10):
                    time.sleep(self.config.calc_interval)
                    continue

                current_time = time.time()

                self._calculate_individual_risk_factors()

                if current_time - last_cov_calc_time >= cov_calc_interval:
                    self._calculate_portfolio_metrics()
                    last_cov_calc_time = current_time

                self._publish_results()

            except Exception as e:
                logger.error(f"Error in calculation loop: {e}", exc_info=True)

            time.sleep(self.config.calc_interval)

        logger.info("Calculation loop stopped")

    def _calculate_individual_risk_factors(self):
        market_prices = self.data_manager.get_market_prices()

        with self._lock:
            for symbol in self.config.symbols:
                if not self.data_manager.has_enough_data(symbol, min_points=10):
                    continue

                prices = self.data_manager.get_prices(symbol)
                factors = self.risk_calculator.calculate_all_factors(
                    prices,
                    market_prices if len(market_prices) > 0 else None
                )

                fee_data = self.data_manager.fee_data.get(symbol, {})
                if fee_data:
                    factors["maker_fee"] = fee_data.get("makerFee", 0)
                    factors["taker_fee"] = fee_data.get("takerFee", 0)
                    factors["funding_rate"] = fee_data.get("fundingRate", 0)

                self._risk_cache[symbol] = factors

    def _calculate_portfolio_metrics(self):
        returns_dict = self.data_manager.get_all_returns()

        with self._lock:
            self._covariance_matrix = self.portfolio_calculator.calculate_covariance_matrix(
                returns_dict
            )
            self._correlation_matrix = self.portfolio_calculator.calculate_correlation_matrix(
                returns_dict
            )

            n = len(self.config.symbols)
            if n > 0:
                equal_weights = np.ones(n) / n

                individual_vols = np.array([
                    self._risk_cache.get(s, {}).get("volatility", 0)
                    for s in self.config.symbols
                ])

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
                    "portfolio_volatility": port_vol,
                    "portfolio_var_95": port_var,
                    "diversification_ratio": div_ratio,
                    "risk_contributions": {
                        s: float(rc)
                        for s, rc in zip(self.config.symbols, risk_contrib)
                    }
                }

                self._risk_cache["__portfolio__"] = portfolio_metrics

    def _publish_results(self):
        with self._lock:
            for symbol, factors in self._risk_cache.items():
                if symbol == "__portfolio__":
                    key = "risk:portfolio"
                    self.redis_client.hset(key, mapping=self._flatten_dict(factors))
                else:
                    key = f"risk:{symbol}"
                    self.redis_client.hset(key, mapping={
                        k: str(v) if not isinstance(v, str) else v
                        for k, v in factors.items()
                    })

            if self._covariance_matrix.size > 0:
                cov_data = json.dumps({
                    "symbols": self.config.symbols,
                    "matrix": self._covariance_matrix.tolist(),
                    "timestamp": int(time.time() * 1000)
                })
                self.redis_client.set("risk:covariance_matrix", cov_data)

            if self._correlation_matrix.size > 0:
                corr_data = json.dumps({
                    "symbols": self.config.symbols,
                    "matrix": self._correlation_matrix.tolist(),
                    "timestamp": int(time.time() * 1000)
                })
                self.redis_client.set("risk:correlation_matrix", corr_data)

        self.redis_client.publish("channel:risk", json.dumps({
            "type": "risk_update",
            "timestamp": int(time.time() * 1000)
        }))

    def _flatten_dict(self, d: dict, parent_key: str = "", sep: str = ".") -> dict:
        items = {}
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.update(self._flatten_dict(v, new_key, sep))
            else:
                items[new_key] = str(v) if not isinstance(v, str) else v
        return items

    def get_risk_factors(self, symbol: str) -> dict:
        with self._lock:
            return self._risk_cache.get(symbol, {}).copy()

    def get_covariance_matrix(self) -> dict:
        with self._lock:
            if self._covariance_matrix.size == 0:
                return {"symbols": [], "matrix": []}
            return {
                "symbols": self.config.symbols.copy(),
                "matrix": self._covariance_matrix.tolist()
            }

    def get_correlation_matrix(self) -> dict:
        with self._lock:
            if self._correlation_matrix.size == 0:
                return {"symbols": [], "matrix": []}
            return {
                "symbols": self.config.symbols.copy(),
                "matrix": self._correlation_matrix.tolist()
            }


def main():
    engine = QuantCalcEngine()
    engine.start()


if __name__ == "__main__":
    main()
