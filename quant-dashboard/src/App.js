import React, { useState, useEffect, useCallback } from 'react';
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

function App() {
  const [riskData, setRiskData] = useState({});
  const [selectedSymbol, setSelectedSymbol] = useState('BTC');
  const [connectionStatus, setConnectionStatus] = useState('connecting');
  const [lastUpdate, setLastUpdate] = useState(null);

  const handleMessage = useCallback((data) => {
    if (data.type === 'risk_factor' && data.symbol) {
      setRiskData(prev => ({
        ...prev,
        [data.symbol]: {
          ...prev[data.symbol],
          ...data.data,
          timestamp: data.timestamp || Date.now()
        }
      }));
      setLastUpdate(Date.now());
    }
  }, []);

  const { status } = useWebSocket('ws://localhost:8080/ws', handleMessage);

  useEffect(() => {
    setConnectionStatus(status);
  }, [status]);

  return (
    <div className="app">
      <Header
        connectionStatus={connectionStatus}
        lastUpdate={lastUpdate}
        symbolCount={Object.keys(riskData).length}
      />

      <main className="main-content">
        <OverviewCards riskData={riskData} symbols={SYMBOLS} />

        <div className="dashboard-grid">
          <div className="panel radar-panel">
            <h2 className="panel-title">风险雷达图</h2>
            <div className="symbol-selector">
              {SYMBOLS.map(symbol => (
                <button
                  key={symbol}
                  className={`symbol-btn ${selectedSymbol === symbol ? 'active' : ''}`}
                  onClick={() => setSelectedSymbol(symbol)}
                >
                  {symbol}
                </button>
              ))}
            </div>
            <RiskRadar
              data={riskData[selectedSymbol] || {}}
              symbol={selectedSymbol}
            />
          </div>

          <div className="panel matrix-panel">
            <h2 className="panel-title">资产相关性矩阵</h2>
            <CorrelationMatrix
              riskData={riskData}
              symbols={SYMBOLS}
            />
          </div>
        </div>

        <div className="panel table-panel">
          <h2 className="panel-title">风险因子明细</h2>
          <RiskTable
            riskData={riskData}
            symbols={SYMBOLS}
          />
        </div>
      </main>
    </div>
  );
}

export default App;
