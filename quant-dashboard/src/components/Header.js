import React from 'react';
import './Header.css';

function Header({ connectionStatus, lastUpdate, symbolCount, dataFreshness, staleSymbolCount }) {
  const formatTime = (timestamp) => {
    if (!timestamp) return '--';
    const date = new Date(timestamp);
    return date.toLocaleTimeString('zh-CN', { hour12: false });
  };

  const formatAge = (timestamp) => {
    if (!timestamp) return '--';
    const age = Math.floor((Date.now() - timestamp) / 1000);
    if (age < 60) return `${age}s前`;
    return `${Math.floor(age / 60)}m前`;
  };

  const statusConfig = {
    connected: { text: '已连接', color: '#00ff88', dot: '#00ff88' },
    connecting: { text: '连接中', color: '#ffcc00', dot: '#ffcc00' },
    disconnected: { text: '已断开', color: '#ff4444', dot: '#ff4444' }
  };

  const freshnessConfig = {
    fresh: { text: '实时', color: '#00ff88' },
    partial: { text: '部分延迟', color: '#88ccff' },
    stale: { text: '数据延迟', color: '#ffcc00' },
    critical: { text: '数据过期', color: '#ff4444' },
    unknown: { text: '等待数据', color: '#778da9' }
  };

  const connStatus = statusConfig[connectionStatus] || statusConfig.disconnected;
  const freshness = freshnessConfig[dataFreshness] || freshnessConfig.unknown;

  return (
    <header className="header">
      <div className="header-left">
        <div className="logo">
          <span className="logo-icon">◆</span>
          <span className="logo-text">Quant Risk</span>
        </div>
        <div className="header-subtitle">高频量化风险因子实时监控系统</div>
      </div>

      <div className="header-right">
        <div className="status-item">
          <span className="status-label">监控资产</span>
          <span className="status-value">
            {symbolCount} 个
            {staleSymbolCount > 0 && (
              <span className="stale-count" style={{ color: '#ffcc00', marginLeft: 4 }}>
                ({staleSymbolCount}延迟)
              </span>
            )}
          </span>
        </div>
        <div className="status-item">
          <span className="status-label">最后更新</span>
          <span className="status-value">{formatTime(lastUpdate)}</span>
          <span className="status-age" style={{ color: freshness.color }}>
            {formatAge(lastUpdate)}
          </span>
        </div>
        <div className="status-item">
          <span className="status-label">数据新鲜度</span>
          <span className="status-value" style={{ color: freshness.color }}>
            {freshness.text}
          </span>
        </div>
        <div className="status-item connection-status">
          <span
            className="status-dot"
            style={{ backgroundColor: connStatus.dot }}
          />
          <span className="status-label" style={{ color: connStatus.color }}>
            {connStatus.text}
          </span>
        </div>
      </div>
    </header>
  );
}

export default Header;
