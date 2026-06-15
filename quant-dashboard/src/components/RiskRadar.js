import React from 'react';
import ReactECharts from 'echarts-for-react';
import './RiskRadar.css';

const RADAR_FACTORS = [
  { key: 'volatility', label: '波动率', max: 1, invert: false },
  { key: 'sharpe_ratio', label: '夏普比率', max: 5, invert: false },
  { key: 'max_drawdown', label: '最大回撤', max: 1, invert: true },
  { key: 'var_95', label: 'VaR(95%)', max: 0.1, invert: true },
  { key: 'sortino_ratio', label: '索提诺比率', max: 5, invert: false },
  { key: 'calmar_ratio', label: '卡玛比率', max: 5, invert: false },
];

function normalizeValue(value, max, invert) {
  if (value === undefined || value === null || isNaN(value)) return 0;
  let normalized = Math.min(Math.abs(value) / max, 1);
  if (invert) {
    normalized = 1 - normalized;
  }
  return Math.round(normalized * 100) / 100;
}

function RiskRadar({ data, symbol }) {
  const indicator = RADAR_FACTORS.map(f => ({
    name: f.label,
    max: 1
  }));

  const values = RADAR_FACTORS.map(f =>
    normalizeValue(data[f.key], f.max, f.invert)
  );

  const rawValues = RADAR_FACTORS.map(f => data[f.key] || 0);

  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(13, 27, 42, 0.9)',
      borderColor: '#415a77',
      textStyle: {
        color: '#e0e1dd',
        fontSize: 12
      },
      formatter: (params) => {
        let result = `<strong>${symbol}</strong><br/>`;
        RADAR_FACTORS.forEach((f, i) => {
          const val = rawValues[i];
          const displayVal = Math.abs(val) > 1
            ? val.toFixed(2)
            : val.toFixed(4);
          result += `${f.label}: ${displayVal}<br/>`;
        });
        return result;
      }
    },
    radar: {
      indicator: indicator,
      shape: 'polygon',
      splitNumber: 4,
      axisName: {
        color: '#778da9',
        fontSize: 12
      },
      splitLine: {
        lineStyle: {
          color: '#415a77',
          type: 'dashed'
        }
      },
      splitArea: {
        show: true,
        areaStyle: {
          color: ['rgba(65, 90, 119, 0.1)', 'rgba(65, 90, 119, 0.05)']
        }
      },
      axisLine: {
        lineStyle: {
          color: '#415a77'
        }
      }
    },
    series: [{
      type: 'radar',
      data: [{
        value: values,
        name: symbol,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: {
          color: '#00d4ff',
          width: 2
        },
        areaStyle: {
          color: {
            type: 'radial',
            x: 0.5,
            y: 0.5,
            r: 0.8,
            colorStops: [
              { offset: 0, color: 'rgba(0, 212, 255, 0.6)' },
              { offset: 1, color: 'rgba(0, 212, 255, 0.1)' }
            ]
          }
        },
        itemStyle: {
          color: '#00d4ff',
          borderColor: '#fff',
          borderWidth: 1
        }
      }]
    }]
  };

  const riskScore = values.reduce((a, b) => a + b, 0) / values.length;
  const riskLevel = riskScore > 0.7 ? '低风险' : riskScore > 0.4 ? '中风险' : '高风险';
  const riskColor = riskScore > 0.7 ? '#00ff88' : riskScore > 0.4 ? '#ffcc00' : '#ff4444';

  return (
    <div className="risk-radar">
      <div className="radar-chart">
        <ReactECharts
          option={option}
          style={{ height: '320px', width: '100%' }}
          opts={{ renderer: 'canvas' }}
        />
      </div>
      <div className="radar-summary">
        <div className="summary-item">
          <span className="summary-label">综合风险评分</span>
          <span className="summary-value" style={{ color: riskColor }}>
            {(riskScore * 100).toFixed(1)}
          </span>
        </div>
        <div className="summary-item">
          <span className="summary-label">风险等级</span>
          <span className="summary-value" style={{ color: riskColor }}>
            {riskLevel}
          </span>
        </div>
        <div className="summary-item">
          <span className="summary-label">当前价格</span>
          <span className="summary-value">
            {data.current_price ? data.current_price.toFixed(2) : '--'}
          </span>
        </div>
      </div>
    </div>
  );
}

export default RiskRadar;
