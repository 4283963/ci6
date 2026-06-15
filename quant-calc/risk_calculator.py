import numpy as np
from scipy import stats
from typing import Dict, Optional, Tuple
import warnings

warnings.filterwarnings('ignore')


class RiskCalculator:
    def __init__(self, risk_free_rate: float = 0.02, confidence_level: float = 0.95):
        self.risk_free_rate = risk_free_rate
        self.confidence_level = confidence_level

    def calculate_returns(self, prices: np.ndarray) -> np.ndarray:
        if len(prices) < 2:
            return np.array([])
        return np.diff(prices) / prices[:-1]

    def calculate_volatility(self, returns: np.ndarray, annualized: bool = True) -> float:
        if len(returns) < 2:
            return 0.0
        vol = np.std(returns, ddof=1)
        if annualized:
            vol *= np.sqrt(365 * 24 * 60 * 60 / 5)
        return float(vol)

    def calculate_sharpe_ratio(self, returns: np.ndarray, annualized: bool = True) -> float:
        if len(returns) < 2:
            return 0.0
        vol = self.calculate_volatility(returns, annualized)
        if vol == 0:
            return 0.0
        mean_return = np.mean(returns)
        if annualized:
            mean_return *= 365 * 24 * 60 * 60 / 5
        excess_return = mean_return - self.risk_free_rate
        return float(excess_return / vol)

    def calculate_max_drawdown(self, prices: np.ndarray) -> Tuple[float, float, float]:
        if len(prices) < 2:
            return 0.0, 0.0, 0.0
        peak = np.maximum.accumulate(prices)
        drawdown = (prices - peak) / peak
        max_dd = float(np.min(drawdown))
        peak_idx = int(np.argmax(peak))
        trough_idx = int(np.argmin(drawdown[peak_idx:]) + peak_idx)
        recovery_factor = float(np.abs((prices[-1] - prices[trough_idx]) / (prices[peak_idx] - prices[trough_idx]))) if prices[peak_idx] != prices[trough_idx] else 0.0
        return max_dd, recovery_factor, float(trough_idx / len(prices))

    def calculate_var(self, returns: np.ndarray, method: str = "parametric") -> float:
        if len(returns) < 2:
            return 0.0
        if method == "parametric":
            z_score = stats.norm.ppf(1 - self.confidence_level)
            var = np.mean(returns) + z_score * np.std(returns, ddof=1)
        elif method == "historical":
            var = np.percentile(returns, (1 - self.confidence_level) * 100)
        else:
            raise ValueError(f"Unknown VaR method: {method}")
        return float(abs(var))

    def calculate_cvar(self, returns: np.ndarray) -> float:
        if len(returns) < 2:
            return 0.0
        var = self.calculate_var(returns, method="historical")
        returns_below_var = returns[returns <= -var]
        if len(returns_below_var) == 0:
            return var
        return float(np.mean(np.abs(returns_below_var)))

    def calculate_beta(self, returns: np.ndarray, market_returns: np.ndarray) -> float:
        if len(returns) < 2 or len(market_returns) < 2:
            return 0.0
        min_len = min(len(returns), len(market_returns))
        if min_len < 2:
            return 0.0
        r = returns[-min_len:]
        m = market_returns[-min_len:]
        cov = np.cov(r, m, ddof=1)[0, 1]
        var_m = np.var(m, ddof=1)
        if var_m == 0:
            return 0.0
        return float(cov / var_m)

    def calculate_information_ratio(self, returns: np.ndarray, benchmark_returns: np.ndarray) -> float:
        if len(returns) < 2 or len(benchmark_returns) < 2:
            return 0.0
        min_len = min(len(returns), len(benchmark_returns))
        if min_len < 2:
            return 0.0
        active_return = returns[-min_len:] - benchmark_returns[-min_len:]
        tracking_error = np.std(active_return, ddof=1)
        if tracking_error == 0:
            return 0.0
        return float(np.mean(active_return) / tracking_error)

    def calculate_skewness(self, returns: np.ndarray) -> float:
        if len(returns) < 3:
            return 0.0
        return float(stats.skew(returns, bias=False))

    def calculate_kurtosis(self, returns: np.ndarray) -> float:
        if len(returns) < 4:
            return 0.0
        return float(stats.kurtosis(returns, bias=False, fisher=True))

    def calculate_downside_deviation(self, returns: np.ndarray, mar: float = 0.0) -> float:
        if len(returns) < 2:
            return 0.0
        downside = returns[returns < mar]
        if len(downside) == 0:
            return 0.0
        return float(np.sqrt(np.mean((downside - mar) ** 2)))

    def calculate_sortino_ratio(self, returns: np.ndarray) -> float:
        if len(returns) < 2:
            return 0.0
        downside_dev = self.calculate_downside_deviation(returns)
        if downside_dev == 0:
            return 0.0
        mean_return = np.mean(returns)
        excess_return = mean_return - self.risk_free_rate / (365 * 24 * 60 * 60 / 5)
        return float(excess_return / downside_dev)

    def calculate_calmar_ratio(self, prices: np.ndarray) -> float:
        if len(prices) < 2:
            return 0.0
        max_dd, _, _ = self.calculate_max_drawdown(prices)
        if max_dd == 0:
            return 0.0
        annual_return = self._calculate_annual_return(prices)
        return float(annual_return / abs(max_dd))

    def _calculate_annual_return(self, prices: np.ndarray) -> float:
        if len(prices) < 2:
            return 0.0
        total_return = (prices[-1] - prices[0]) / prices[0]
        periods_per_year = 365 * 24 * 60 * 60 / 5
        annualized = (1 + total_return) ** (periods_per_year / len(prices)) - 1
        return float(annualized)

    def calculate_all_factors(self, prices: np.ndarray, market_prices: Optional[np.ndarray] = None) -> Dict[str, float]:
        returns = self.calculate_returns(prices)
        max_dd, recovery, dd_position = self.calculate_max_drawdown(prices)

        factors = {
            "volatility": self.calculate_volatility(returns),
            "sharpe_ratio": self.calculate_sharpe_ratio(returns),
            "max_drawdown": max_dd,
            "recovery_factor": recovery,
            "drawdown_position": dd_position,
            "var_95": self.calculate_var(returns, method="parametric"),
            "cvar_95": self.calculate_cvar(returns),
            "skewness": self.calculate_skewness(returns),
            "kurtosis": self.calculate_kurtosis(returns),
            "downside_deviation": self.calculate_downside_deviation(returns),
            "sortino_ratio": self.calculate_sortino_ratio(returns),
            "calmar_ratio": self.calculate_calmar_ratio(prices),
            "annual_return": self._calculate_annual_return(prices),
            "current_price": float(prices[-1]) if len(prices) > 0 else 0.0,
        }

        if market_prices is not None:
            market_returns = self.calculate_returns(market_prices)
            factors["beta"] = self.calculate_beta(returns, market_returns)
            factors["information_ratio"] = self.calculate_information_ratio(returns, market_returns)

        return {k: round(v, 6) for k, v in factors.items()}


class PortfolioRiskCalculator:
    def __init__(self, risk_calculator: RiskCalculator):
        self.risk_calculator = risk_calculator

    def _align_and_stack_arrays(
        self,
        arrays: Dict[str, np.ndarray],
        min_required: int = 2
    ) -> Optional[Tuple[list, np.ndarray]]:
        symbols = list(arrays.keys())
        if len(symbols) == 0:
            return None

        valid_lengths = []
        for symbol in symbols:
            arr = arrays[symbol]
            if arr is None or not isinstance(arr, np.ndarray):
                valid_lengths.append(0)
            elif arr.ndim != 1:
                valid_lengths.append(0)
            else:
                valid_lengths.append(len(arr))

        min_len = min(valid_lengths) if valid_lengths else 0
        if min_len < min_required:
            return None

        aligned = []
        for symbol in symbols:
            arr = arrays[symbol]
            sliced = arr[-min_len:].astype(np.float64)
            if np.any(~np.isfinite(sliced)):
                sliced = np.nan_to_num(sliced, nan=0.0, posinf=0.0, neginf=0.0)
            aligned.append(sliced)

        try:
            stacked = np.vstack(aligned)
            if stacked.ndim != 2 or stacked.shape[0] != len(symbols) or stacked.shape[1] != min_len:
                return None
            return symbols, stacked
        except (ValueError, TypeError):
            return None

    def calculate_covariance_matrix(self, returns_dict: Dict[str, np.ndarray]) -> np.ndarray:
        symbols = list(returns_dict.keys())
        n = len(symbols)
        if n == 0:
            return np.array([])

        result = self._align_and_stack_arrays(returns_dict, min_required=2)
        if result is None:
            cov = np.eye(n) * 0.01
            np.fill_diagonal(cov, 0.0)
            return cov

        _, stacked = result
        try:
            cov_matrix = np.cov(stacked, ddof=1)
            if not np.all(np.isfinite(cov_matrix)):
                cov_matrix = np.nan_to_num(cov_matrix, nan=0.0, posinf=0.0, neginf=0.0)
                cov_matrix = (cov_matrix + cov_matrix.T) / 2
            return cov_matrix
        except (ValueError, TypeError, FloatingPointError) as e:
            import logging
            logging.getLogger("quant-calc").warning(f"np.cov failed, falling back to diag matrix: {e}")
            variances = np.var(stacked, axis=1, ddof=1)
            return np.diag(np.nan_to_num(variances, nan=0.01))

    def calculate_correlation_matrix(self, returns_dict: Dict[str, np.ndarray]) -> np.ndarray:
        symbols = list(returns_dict.keys())
        n = len(symbols)
        if n == 0:
            return np.array([])

        result = self._align_and_stack_arrays(returns_dict, min_required=3)
        if result is None:
            return np.eye(n)

        _, stacked = result
        try:
            corr_matrix = np.corrcoef(stacked)
            if not np.all(np.isfinite(corr_matrix)):
                corr_matrix = np.nan_to_num(corr_matrix, nan=0.0, posinf=1.0, neginf=-1.0)
                corr_matrix = (corr_matrix + corr_matrix.T) / 2
                np.fill_diagonal(corr_matrix, 1.0)
            np.clip(corr_matrix, -1.0, 1.0, out=corr_matrix)
            return corr_matrix
        except (ValueError, TypeError, FloatingPointError) as e:
            import logging
            logging.getLogger("quant-calc").warning(f"np.corrcoef failed, falling back to identity: {e}")
            return np.eye(n)

    def calculate_portfolio_volatility(
        self,
        weights: np.ndarray,
        cov_matrix: np.ndarray
    ) -> float:
        if len(weights) == 0 or len(cov_matrix) == 0:
            return 0.0
        return float(np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights))))

    def calculate_portfolio_var(
        self,
        weights: np.ndarray,
        cov_matrix: np.ndarray,
        portfolio_value: float = 1.0
    ) -> float:
        port_vol = self.calculate_portfolio_volatility(weights, cov_matrix)
        z_score = stats.norm.ppf(1 - self.risk_calculator.confidence_level)
        return float(abs(z_score) * port_vol * portfolio_value)

    def calculate_diversification_ratio(
        self,
        weights: np.ndarray,
        cov_matrix: np.ndarray,
        individual_vols: np.ndarray
    ) -> float:
        if len(weights) == 0:
            return 0.0
        weighted_vol = np.dot(weights, individual_vols)
        portfolio_vol = self.calculate_portfolio_volatility(weights, cov_matrix)
        if portfolio_vol == 0:
            return 0.0
        return float(weighted_vol / portfolio_vol)

    def calculate_marginal_risk_contribution(
        self,
        weights: np.ndarray,
        cov_matrix: np.ndarray
    ) -> np.ndarray:
        if len(weights) == 0:
            return np.array([])
        port_vol = self.calculate_portfolio_volatility(weights, cov_matrix)
        if port_vol == 0:
            return np.zeros_like(weights)
        mrc = np.dot(cov_matrix, weights) / port_vol
        return mrc

    def calculate_risk_contribution(
        self,
        weights: np.ndarray,
        cov_matrix: np.ndarray
    ) -> np.ndarray:
        if len(weights) == 0:
            return np.array([])
        mrc = self.calculate_marginal_risk_contribution(weights, cov_matrix)
        rc = weights * mrc
        port_vol = self.calculate_portfolio_volatility(weights, cov_matrix)
        if port_vol > 0:
            rc = rc / port_vol
        return rc
