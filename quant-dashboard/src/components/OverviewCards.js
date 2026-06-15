import React from 'react';
import './OverviewCards.css';

function OverviewCards({ riskData, symbols }) {
  const calcMetrics = () => {
    const dataPoints = symbols.filter(s => riskData[s] && riskData[s].volatility);

    if (dataPoints.length === 0) {
      return {
        avgVolatility: 0,
        avgSharpe: 0,
        avgMaxDD: 0,
        riskScore: 0,
        totalAssets: symbols.length,
        activeAssets: 0
      };
    }

    const avgVolatility = dataPoints.reduce((sum, s) => sum + (riskData[s].volatility || 0), 0) / dataPoints.length;
    const avgSharpe = dataPoints.reduce((sum, s) => sum + (riskData[s].sharpe_ratio || 0), 0) / dataPoints.length;
    const avgMaxDD = dataPoints.reduce((sum, s) => sum + Math.abs(riskData[s].max_drawdown || 0), 0) / dataPoints.length;

    const volScore = Math.max(0, 1 - avgVolatility / 1);
    const sharpeScore = Math.min(1, Math.max(0, avgSharpe / 3));
    const ddScore = Math.max(0, 1 - avgMaxDD / 0.5);
    const riskScore = (volScore + sharpeScore + ddScore) / 3;

    return {
      avgVolatility,
      avgSharpe,
      avgMaxDD,
      riskScore,
      totalAssets: symbols.length,
      activeAssets: dataPoints.length
    };
  };

  const metrics = calcMetrics();

  const cards = [
    {
      label: '监控资产',
      value: `${metrics.activeAssets}/${metrics.totalAssets}`,
      sublabel: '活跃资产/总数',
      color: '#00d4ff',
      icon: '◈'
    },
    {
      label: '平均波动率',
      value: (metrics.avgVolatility * 100).toFixed(2) + '%',
      sublabel: '年化波动率',
      color: metrics.avgVolatility > 0.5 ? '#ff4444' : '#00ff88',
      icon: '⚡'
    },
    {
      label: '平均夏普比率',
      value: metrics.avgSharpe.toFixed(2),
      sublabel: '风险调整收益',
      color: metrics.avgSharpe > 1 ? '#00ff88' : '#ffcc00',
      icon: '📈'
    },
    {
      label: '综合风险评分',
      value: (metrics.riskScore * 100).toFixed(1),
      sublabel: '越高越安全',
      color: metrics.riskScore > 0.7 ? '#00ff88' : metrics.riskScore > 0.4 ? '#ffcc00' : '#ff4444',
      icon: '🛡️'
    }
  ];

  return (
    <div className="overview-cards">
      {cards.map((card, index) => (
        <div key={index} className="overview-card" style={{ borderColor: card.color + '40' }}>
          <div className="card-icon" style={{ color: card.color }}>
            {card.icon}
          </div>
          <div className="card-content">
            <div className="card-label">{card.label}</div>
            <div className="card-value" style={{ color: card.color }}>
              {card.value}
            </div>
            <div className="card-sublabel">{card.sublabel}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

export default OverviewCards;
