import React, { useState, useMemo, useCallback } from 'react';
import './WeightPanel.css';

const SYMBOLS = [
  { symbol: 'BTC', color: '#f7931a' },
  { symbol: 'ETH', color: '#627eea' },
  { symbol: 'SOL', color: '#00ffa3' },
  { symbol: 'BNB', color: '#f3ba2f' },
  { symbol: 'XRP', color: '#23292f' },
  { symbol: 'ADA', color: '#0033ad' },
  { symbol: 'DOGE', color: '#c3a634' },
  { symbol: 'DOT', color: '#e6007a' },
  { symbol: 'AVAX', color: '#e84142' },
  { symbol: 'LINK', color: '#2a5ada' },
];

const DEFAULT_WEIGHT = 10;

function WeightPanel({ onWeightsChange, riskData = {} }) {
  const [weights, setWeights] = useState(() => {
    const initial = {};
    SYMBOLS.forEach(s => {
      initial[s.symbol] = DEFAULT_WEIGHT;
    });
    return initial;
  });
  const [activeTab, setActiveTab] = useState('manual');

  const totalWeight = useMemo(() => {
    return Object.values(weights).reduce((sum, w) => sum + w, 0);
  }, [weights]);

  const normalizedWeights = useMemo(() => {
    const result = {};
    if (totalWeight === 0) return result;
    Object.entries(weights).forEach(([symbol, w]) => {
      result[symbol] = w / totalWeight;
    };
    return result;
  }, [weights, totalWeight]);

  const handleWeightChange = useCallback((symbol, value) => {
    setWeights(prev => {
      const next = { ...prev, [symbol]: Number(value) };
      return next;
    });
  }, []);

  const handleSliderChange = useCallback((symbol, value) => {
    const numValue = Number(value);
    setWeights(prev => ({ ...prev, [symbol]: numValue }));
  }, []);

  const handleSliderCommit = useCallback(() => {
    onWeightsChange?.(normalizedWeights);
  }, [normalizedWeights, onWeightsChange]);

  const resetToEqual = useCallback(() => {
    const equal = {};
    SYMBOLS.forEach(s => { equal[s.symbol] = 10;
    });
    setWeights(equal);
  }, []);

  const setMaxWeight = useCallback((symbol, value) => {
    setWeights(prev => ({ ...prev, [symbol]: value }));
  }, []);

  React.useEffect(() => {
    const timer = setTimeout(() => {
      onWeightsChange?.(normalizedWeights);
    }, 50);
    return () => clearTimeout(timer);
  }, [normalizedWeights, onWeightsChange]);

  const sortedByWeight = useMemo(() => {
    return [...SYMBOLS].sort((a, b) => weights[b.symbol] - weights[a.symbol]);
  }, [weights]);

  const topThree = sortedByWeight.slice(0, 3);

  return (
    <div className="weight-panel">
      <div className="panel-header">
      <h3 className="panel-title">资产权重配置</h3>
      <div className="weight-tabs">
        <button
          className={`tab-btn ${activeTab === 'manual' ? 'active' : ''}`}
          onClick={() => setActiveTab('manual')}
        >
          手动
        </button>
        <button
          className={`tab-btn ${activeTab === 'preset' ? 'active' : ''}`}
          onClick={() => setActiveTab('preset')}
        >
          预设
        </button>
      </div>
    </div>

    <div className="panel-summary">
      <div className="summary-row">
        <span className="summary-label">总资产数</span>
        <span className="summary-value">{SYMBOLS.length} 个</span>
      </div>
      <div className="summary-row">
        <span className="summary-label">权重总和</span>
        <span className={`summary-value ${totalWeight === 0 ? 'zero' : ''}`}>
          {totalWeight.toFixed(0)}
        </span>
      </div>
    </div>

    <div className="top-holdings">
      <div className="holdings-title">持仓占比 Top 3</div>
      <div className="holdings-list">
        {topThree.map((item, idx) => (
          <div key={item.symbol} className="holding-item">
            <span className="holding-rank">{idx + 1}.</span>
            <span
              className="holding-dot" style={{ backgroundColor: item.color }} />
            <span className="holding-symbol">{item.symbol}</span>
            <span className="holding-weight">
              {(normalizedWeights[item.symbol] * 100).toFixed(1)}%
            </span>
          </div>
        ))}
      </div>
    </div>

    <div className="weight-list">
      {SYMBOLS.map(item => {
        const weight = weights[item.symbol] || 0;
        const pct = totalWeight > 0 ? (weight / totalWeight * 100) : 0;
        const risk = riskData[item.symbol];
        const volColor = risk?.volatility
          ? (risk.volatility > 0.8 ? '#ff4444' : risk.volatility > 0.5 ? '#ffcc00' : '#00ff88')
          : '#778da9';

        return (
          <div key={item.symbol} className="weight-item">
            <div className="weight-item-header">
              <div className="weight-item-left">
                <span
                  className="weight-color-dot"
                  style={{ backgroundColor: item.color }}
                />
                <span className="weight-symbol">{item.symbol}</span>
                {risk && (
                  <span
                  className="weight-vol-badge"
                  style={{ color: volColor }}
                  title="波动率"
                  >
                    {(risk.volatility * 100).toFixed(1)}%
                  </span>
                )}
              </div>
              <div className="weight-item-right">
                <span className="weight-percent">{pct.toFixed(1)}%</span>
              </div>
            </div>

            <div className="weight-slider-container">
              <input
                type="range"
                min="0"
                max="100"
                step="1"
                value={weight}
                onChange={(e) => handleSliderChange(item.symbol, e.target.value)}
                onMouseUp={handleSliderCommit}
                onTouchEnd={handleSliderCommit}
                className="weight-slider"
                style={{
                  '--slider-color': item.color,
                  '--slider-progress': `${weight}%`
                }}
              />
              <div className="weight-quick-btns">
                <button className="quick-btn" onClick={() => setMaxWeight(item.symbol, 0)}>0</button>
                <button className="quick-btn" onClick={() => setMaxWeight(item.symbol, 10)}>10</button>
                <button className="quick-btn" onClick={() => setMaxWeight(item.symbol, 50)}>50</button>
              </div>
            </div>

            <div className="weight-bar-bg">
              <div
                className="weight-bar-fill"
                style={{
                  width: `${pct}%`,
                  backgroundColor: item.color,
                  boxShadow: `0 0 8px ${item.color}40`
                }}
              />
            </div>
          </div>
        );
      })}
    </div>

    <div className="panel-actions">
      <button className="action-btn action-btn--secondary" onClick={resetToEqual}>
        等权重置
      </button>
      <button className="action-btn action-btn--primary" onClick={handleSliderCommit}>
        应用权重
      </button>
    </div>
  </div>
);
}

export default WeightPanel;
