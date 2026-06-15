import React from 'react';
import ReactECharts from 'echarts-for-react';
import './CorrelationMatrix.css';

function CorrelationMatrix({ riskData, symbols }) {
  const generateMockCorrelation = () => {
    const n = symbols.length;
    const matrix = [];
    for (let i = 0; i < n; i++) {
      const row = [];
      for (let j = 0; j < n; j++) {
        if (i === j) {
          row.push(1);
        } else if (riskData[symbols[i]] && riskData[symbols[j]]) {
          const volI = riskData[symbols[i]].volatility || 0.5;
          const volJ = riskData[symbols[j]].volatility || 0.5;
          const baseCorr = 0.3 + Math.random() * 0.5;
          row.push(Math.min(0.95, Math.max(0.1, baseCorr * (1 + (volI + volJ) / 4))));
        } else {
          row.push(0.5 + (Math.random() - 0.5) * 0.3);
        }
      }
      matrix.push(row);
    }
    return matrix;
  };

  const matrix = generateMockCorrelation();

  const data = [];
  for (let i = 0; i < symbols.length; i++) {
    for (let j = 0; j < symbols.length; j++) {
      data.push([j, i, matrix[i][j]]);
    }
  }

  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      position: 'top',
      backgroundColor: 'rgba(13, 27, 42, 0.9)',
      borderColor: '#415a77',
      textStyle: {
        color: '#e0e1dd',
        fontSize: 12
      },
      formatter: (params) => {
        return `${symbols[params.value[1]]} × ${symbols[params.value[0]]}<br/>
                相关系数: ${params.value[2].toFixed(3)}`;
      }
    },
    grid: {
      left: '12%',
      right: '5%',
      top: '5%',
      bottom: '15%'
    },
    xAxis: {
      type: 'category',
      data: symbols,
      axisLabel: {
        color: '#778da9',
        fontSize: 10,
        rotate: 45
      },
      axisLine: {
        lineStyle: {
          color: '#415a77'
        }
      },
      splitLine: {
        show: false
      }
    },
    yAxis: {
      type: 'category',
      data: symbols,
      axisLabel: {
        color: '#778da9',
        fontSize: 10
      },
      axisLine: {
        lineStyle: {
          color: '#415a77'
        }
      },
      splitLine: {
        show: false
      }
    },
    visualMap: {
      min: 0,
      max: 1,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: '0%',
      textStyle: {
        color: '#778da9',
        fontSize: 10
      },
      inRange: {
        color: ['#0d1b2a', '#00d4ff', '#00ff88']
      },
      show: false
    },
    series: [{
      type: 'heatmap',
      data: data,
      label: {
        show: true,
        color: '#e0e1dd',
        fontSize: 9,
        formatter: (params) => params.value[2].toFixed(2)
      },
      emphasis: {
        itemStyle: {
          shadowBlur: 10,
          shadowColor: 'rgba(0, 212, 255, 0.5)'
        }
      }
    }]
  };

  const avgCorrelation = matrix.flat().filter((_, i) => {
    const row = Math.floor(i / symbols.length);
    const col = i % symbols.length;
    return row !== col;
  }).reduce((a, b) => a + b, 0) / (symbols.length * (symbols.length - 1));

  return (
    <div className="correlation-matrix">
      <ReactECharts
        option={option}
        style={{ height: '350px', width: '100%' }}
        opts={{ renderer: 'canvas' }}
      />
      <div className="matrix-summary">
        <div className="matrix-stat">
          <span className="stat-label">平均相关系数</span>
          <span className="stat-value">{avgCorrelation.toFixed(3)}</span>
        </div>
        <div className="matrix-stat">
          <span className="stat-label">资产数量</span>
          <span className="stat-value">{symbols.length}</span>
        </div>
      </div>
    </div>
  );
}

export default CorrelationMatrix;
