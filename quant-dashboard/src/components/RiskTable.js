import React from 'react';
import './RiskTable.css';

const FACTOR_CONFIG = [
  { key: 'volatility', label: '波动率', format: 'percent', decimals: 4 },
  { key: 'sharpe_ratio', label: '夏普比率', format: 'number', decimals: 2 },
  { key: 'max_drawdown', label: '最大回撤', format: 'percent', decimals: 4, invert: true },
  { key: 'var_95', label: 'VaR(95%)', format: 'percent', decimals: 4, invert: true },
  { key: 'cvar_95', label: 'CVaR(95%)', format: 'percent', decimals: 4, invert: true },
  { key: 'sortino_ratio', label: '索提诺比率', format: 'number', decimals: 2 },
  { key: 'calmar_ratio', label: '卡玛比率', format: 'number', decimals: 2 },
  { key: 'skewness', label: '偏度', format: 'number', decimals: 3 },
  { key: 'kurtosis', label: '峰度', format: 'number', decimals: 2 },
  { key: 'beta', label: 'Beta系数', format: 'number', decimals: 3 },
];

function formatValue(value, format, decimals) {
  if (value === undefined || value === null || isNaN(value)) {
    return '--';
  }
  if (format === 'percent') {
    return (value * 100).toFixed(decimals - 2) + '%';
  }
  return value.toFixed(decimals);
}

function getValueColor(value, invert) {
  if (value === undefined || value === null || isNaN(value)) {
    return '#778da9';
  }
  const isPositive = invert ? value < 0 : value > 0;
  return isPositive ? '#00ff88' : '#ff4444';
}

function RiskTable({ riskData, symbols, staleSymbols = new Set() }) {
  return (
    <div className="risk-table-container">
      <table className="risk-table">
        <thead>
          <tr>
            <th className="sticky-col">资产</th>
            {FACTOR_CONFIG.map(factor => (
              <th key={factor.key}>{factor.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {symbols.map(symbol => {
            const data = riskData[symbol] || {};
            const isStale = staleSymbols.has(symbol) || data.stale;
            return (
              <tr
                key={symbol}
                className={`table-row ${isStale ? 'table-row--stale' : ''}`}
              >
                <td className="sticky-col symbol-cell">
                  <span className="symbol-name">{symbol}</span>
                  {isStale && <span className="stale-indicator" title="数据过期" />}
                </td>
                {FACTOR_CONFIG.map(factor => (
                  <td key={factor.key}>
                    <span
                      style={{
                        color: isStale ? '#778da9' : getValueColor(data[factor.key], factor.invert),
                        opacity: isStale ? 0.6 : 1
                      }}
                    >
                      {formatValue(data[factor.key], factor.format, factor.decimals)}
                    </span>
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default RiskTable;
