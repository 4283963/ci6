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

function RiskRadar({ data, symbol, isStale = false }) {
  const indicator = RADAR_FACTORS.map(f => ({
    name: f.label,
    max: 1
  }));

  const values = RADAR_FACTORS.map(f =>
    normalizeValue(data[f.key], f.max, f.invert)
  );

  const rawValues = RADAR_FACTORS.map(f => data[f.key] || 0);

  const radarColor = isStale ? '#778da9' : '#00d4ff';
  const areaAlpha = isStale ? '0.3' : '0.6';
  const areaEdgeAlpha = isStale ? '0.05' : '0.1';

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
        let result = `<strong>${symbol}</strong>`;
        if (isStale) {
          result += ' <span style="color:#ffcc00">(数据过期)</span>';
        }
        result += '<br/>';
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
        color: isStale ? '#415a77' : '#778da9',
        fontSize: 12
      },
      splitLine: {
        lineStyle: {
          color: isStale ? '#2b3a55' : '#415a77',
          type: 'dashed'
        }
      },
      splitArea: {
        show: true,
        areaStyle: {
          color: isStale
            ? ['rgba(65, 90, 119, 0.05)', 'rgba(65, 90, 119, 0.02)']
            : ['rgba(65, 90, 119, 0.1)', 'rgba(65, 90, 119, 0.05)']
        }
      },
      axisLine: {
        lineStyle: {
          color: isStale ? '#2b3a55' : '#415a77'
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
          color: radarColor,
          width: 2,
          type: isStale ? 'dashed' : 'solid'
        },
        areaStyle: {
          color: {
            type: 'radial',
            x: 0.5,
            y: 0.5,
            r: 0.8,
            colorStops: [
              { offset: 0, color: isStale ? `rgba(119, 141, 169, ${areaAlpha})` : `rgba(0, 212, 255, ${areaAlpha})` },
              { offset: 1, color: isStale ? `rgba(119, 141, 169, ${areaEdgeAlpha})` : `rgba(0, 212, 255, ${areaEdgeAlpha})` }
            ]
          }
        },
        itemStyle: {
          color: radarColor,
          borderColor: '#fff',
          borderWidth: 1
        }
      }]
    }]
  };

  const riskScore = values.reduce((a, b) => a + b, 0) / values.length;
  const riskLevel = isStale ? '数据过期' : (riskScore > 0.7 ? '低风险' : riskScore > 0.4 ? '中风险' : '高风险');
  const riskColor = isStale ? '#778da9' : (riskScore > 0.7 ? '#00ff88' : riskScore > 0.4 ? '#ffcc00' : '#ff4444');

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
