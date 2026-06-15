import React, { useState, useEffect, useCallback, useRef } from 'react';
import './App.css';
import RiskRadar from './components/RiskRadar';
import RiskTable from './components/RiskTable';
import CorrelationMatrix from './components/CorrelationMatrix';
import Header from './components/Header';
import OverviewCards from './components/OverviewCards';
import useWebSocket from './hooks/useWebSocket';

const SYMBOLS = [
  'BTC', 'ETH', 'SOL', 'BNB', 'XRP',
  'ADA', 'DOGE', 'DOT', 'AVAX', 'LINK'
];

const DATA_STALE_THRESHOLD_MS = 5000;
const DATA_CRITICAL_THRESHOLD_MS = 15000;

function App() {
  const [riskData, setRiskData] = useState({});
  const [selectedSymbol, setSelectedSymbol] = useState('BTC');
  const [connectionStatus, setConnectionStatus] = useState('connecting');
  const [lastUpdate, setLastUpdate] = useState(null);
  const [dataFreshness, setDataFreshness] = useState('unknown');
  const [staleSymbols, setStaleSymbols] = useState(new Set());
  const [errorBanner, setErrorBanner] = useState(null);

  const reconnectCountRef = useRef(0);
  const firstConnectRef = useRef(false);

  const handleMessage = useCallback((data) => {
    if (data.type === 'risk_factor' && data.symbol) {
      const now = Date.now();
      setRiskData(prev => ({
        ...prev,
        [data.symbol]: {
          ...prev[data.symbol],
          ...data.data,
          timestamp: now,
          stale: false
        }
      }));
      setLastUpdate(now);
    }
  }, []);

  const { status, reconnectCount } = useWebSocket('ws://localhost:8080/ws', handleMessage);

  useEffect(() => {
    setConnectionStatus(status);

    if (status === 'connected' && !firstConnectRef.current) {
      firstConnectRef.current = true;
      setErrorBanner(null);
    }
    if (status === 'connected') {
      setErrorBanner(null);
    } else if (status === 'disconnected') {
      if (firstConnectRef.current) {
        setErrorBanner({
          type: 'error',
          message: 'WebSocket 连接已断开，正在尝试自动重连...'
        });
      }
    } else if (status === 'connecting' && firstConnectRef.current) {
      setErrorBanner({
        type: 'warning',
        message: `正在重连 WebSocket (第 ${reconnectCount} 次)...`
      });
    }
  }, [status, reconnectCount]);

  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now();
      const staleSet = new Set();
      let hasCritical = false;

      SYMBOLS.forEach(symbol => {
        const data = riskData[symbol];
        if (!data || !data.timestamp) {
          staleSet.add(symbol);
          hasCritical = true;
          return;
        }
        const age = now - data.timestamp;
        if (age > DATA_STALE_THRESHOLD_MS) {
          staleSet.add(symbol);
        }
        if (age > DATA_CRITICAL_THRESHOLD_MS) {
          hasCritical = true;
        }
      });

      setStaleSymbols(staleSet);

      let freshness = 'fresh';
      if (!lastUpdate || now - lastUpdate > DATA_CRITICAL_THRESHOLD_MS) {
        freshness = 'critical';
      } else if (now - lastUpdate > DATA_STALE_THRESHOLD_MS) {
        freshness = 'stale';
      } else if (staleSet.size > 0) {
        freshness = 'partial';
      }
      setDataFreshness(freshness);

      if (freshness === 'stale' || freshness === 'critical') {
        setRiskData(prev => {
          const updated = { ...prev };
          staleSet.forEach(s => {
            if (updated[s]) {
              updated[s] = { ...updated[s], stale: true };
            }
          });
          return updated;
        });
      }

      if (freshness === 'critical' && !errorBanner) {
        setErrorBanner({
          type: 'warning',
          message: '数据长时间未更新，请检查计算服务是否正常运行'
        });
      } else if (freshness !== 'critical' && errorBanner && errorBanner.type === 'warning' && errorBanner.message.includes('数据长时间')) {
        setErrorBanner(null);
      }

    }, 1000);

    return () => clearInterval(interval);
  }, [riskData, lastUpdate, errorBanner]);

  const dismissBanner = () => setErrorBanner(null);

  return (
    <div className="app">
      {errorBanner && (
        <div className={`error-banner error-banner--${errorBanner.type}`}>
          <span className="error-banner__icon">
            {errorBanner.type === 'error' ? '⚠️' : '⚡'}
          </span>
          <span className="error-banner__message">{errorBanner.message}</span>
          <button className="error-banner__close" onClick={dismissBanner}>✕</button>
        </div>
      )}

      <Header
        connectionStatus={connectionStatus}
        lastUpdate={lastUpdate}
        symbolCount={Object.keys(riskData).length}
        dataFreshness={dataFreshness}
        staleSymbolCount={staleSymbols.size}
      />

      <main className="main-content">
        <OverviewCards
          riskData={riskData}
          symbols={SYMBOLS}
          dataFreshness={dataFreshness}
        />

        <div className="dashboard-grid">
          <div className={`panel radar-panel ${riskData[selectedSymbol]?.stale ? 'panel--stale' : ''}`}>
            <h2 className="panel-title">
              风险雷达图
              {riskData[selectedSymbol]?.stale && (
                <span className="panel-stale-badge">数据过期</span>
              )}
            </h2>
            <div className="symbol-selector">
              {SYMBOLS.map(symbol => (
                <button
                  key={symbol}
                  className={`symbol-btn ${selectedSymbol === symbol ? 'active' : ''} ${staleSymbols.has(symbol) ? 'stale' : ''}`}
                  onClick={() => setSelectedSymbol(symbol)}
                  title={staleSymbols.has(symbol) ? '数据已过期' : '数据正常'}
                >
                  {symbol}
                  {staleSymbols.has(symbol) && <span className="stale-dot" />}
                </button>
              ))}
            </div>
            <RiskRadar
              data={riskData[selectedSymbol] || {}}
              symbol={selectedSymbol}
              isStale={staleSymbols.has(selectedSymbol)}
            />
          </div>

          <div className={`panel matrix-panel ${dataFreshness === 'critical' ? 'panel--stale' : ''}`}>
            <h2 className="panel-title">
              资产相关性矩阵
              {dataFreshness === 'critical' && (
                <span className="panel-stale-badge">数据过期</span>
              )}
            </h2>
            <CorrelationMatrix
              riskData={riskData}
              symbols={SYMBOLS}
            />
          </div>
        </div>

        <div className={`panel table-panel ${dataFreshness === 'critical' ? 'panel--stale' : ''}`}>
          <h2 className="panel-title">
            风险因子明细
            {staleSymbols.size > 0 && (
              <span className="panel-stale-badge">
                {staleSymbols.size}/{SYMBOLS.length} 资产数据过期
              </span>
            )}
          </h2>
          <RiskTable
            riskData={riskData}
            symbols={SYMBOLS}
            staleSymbols={staleSymbols}
          />
        </div>
      </main>
    </div>
  );
}

export default App;
