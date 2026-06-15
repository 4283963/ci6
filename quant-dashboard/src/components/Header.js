import React from 'react';
import './Header.css';

function Header({ connectionStatus, lastUpdate, symbolCount }) {
  const formatTime = (timestamp) => {
    if (!timestamp) return '--';
    const date = new Date(timestamp);
    return date.toLocaleTimeString('zh-CN', { hour12: false });
  };

  const statusConfig = {
    connected: { text: '已连接', color: '#00ff88', dot: '#00ff88' },
    connecting: { text: '连接中', color: '#ffcc00', dot: '#ffcc00' },
    disconnected: { text: '已断开', color: '#ff4444', dot: '#ff4444' }
  };

  const status = statusConfig[connectionStatus] || statusConfig.disconnected;

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
          <span className="status-value">{symbolCount} 个</span>
        </div>
        <div className="status-item">
          <span className="status-label">最后更新</span>
          <span className="status-value">{formatTime(lastUpdate)}</span>
        </div>
        <div className="status-item connection-status">
          <span
            className="status-dot"
            style={{ backgroundColor: status.dot }}
          />
          <span className="status-label" style={{ color: status.color }}>
            {status.text}
          </span>
        </div>
      </div>
    </header>
  );
}

export default Header;
