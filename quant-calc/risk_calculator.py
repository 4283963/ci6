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

    def calculate_covariance_matrix(self, returns_dict: Dict[str, np.ndarray]) -> np.ndarray:
        symbols = list(returns_dict.keys())
        if len(symbols) == 0:
            return np.array([])
        
        min_len = min(len(r) for r in returns_dict.values())
        if min_len < 2:
            return np.zeros((len(symbols), len(symbols)))
        
        aligned_returns = []
        for symbol in symbols:
            aligned_returns.append(returns_dict[symbol][-min_len:])
        
        return np.cov(np.array(aligned_returns), ddof=1)

    def calculate_correlation_matrix(self, returns_dict: Dict[str, np.ndarray]) -> np.ndarray:
        symbols = list(returns_dict.keys())
        if len(symbols) == 0:
            return np.array([])
        
        min_len = min(len(r) for r in returns_dict.values())
        if min_len < 2:
            return np.eye(len(symbols))
        
        aligned_returns = []
        for symbol in symbols:
            aligned_returns.append(returns_dict[symbol][-min_len:])
        
        return np.corrcoef(np.array(aligned_returns))

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
