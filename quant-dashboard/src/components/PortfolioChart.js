import React, { useMemo, useRef, useEffect } from 'react';
import ReactECharts from 'echarts-for-react';
import * as echarts from 'echarts';
import './PortfolioChart.css';

function PortfolioChart({ weights, riskData, symbols, covarianceMatrix, portfolioData, isLocalCalc = false }) {
  const chartRef = useRef(null);

  const portfolioMetrics = useMemo(() => {
    if (portfolioData && portfolioData.expected_return !== undefined) {
      return {
        expectedReturn: portfolioData.expected_return,
        portfolioVol: portfolioData.portfolio_volatility,
        portfolioSharpe: portfolioData.sharpe_ratio,
        diversificationRatio: portfolioData.diversification_ratio,
        var95: portfolioData.var_95,
        cvar95: portfolioData.cvar_95,
        sortinoRatio: portfolioData.sortino_ratio,
        calmarRatio: portfolioData.calmar_ratio,
        maxDrawdown: portfolioData.max_drawdown,
        avgCorrelation: portfolioData.avg_correlation,
        riskContributions: portfolioData.risk_contributions || {},
        varianceDecomposition: portfolioData.variance_decomposition || {},
        numAssets: portfolioData.num_assets || 0,
        isServerCalc: true
      };
    }

    if (!weights || Object.keys(weights).length === 0) {
      return null;
    }

    const validSymbols = symbols.filter(s => riskData[s] && riskData[s].volatility);
    if (validSymbols.length === 0) return null;

    const weightArray = validSymbols.map(s => weights[s] || 0);
    const weightSum = weightArray.reduce((a, b) => a + b, 0);
    if (weightSum === 0) return null;
    const normalizedWeights = weightArray.map(w => w / weightSum);

    const returns = validSymbols.map(s => riskData[s].annual_return || 0);
    const vols = validSymbols.map(s => riskData[s].volatility || 0.01);
    const sharpes = validSymbols.map(s => riskData[s].sharpe_ratio || 0);
    const drawdowns = validSymbols.map(s => Math.abs(riskData[s].max_drawdown || 0));

    const expectedReturn = normalizedWeights.reduce((sum, w, i) => sum + w * returns[i], 0);
    const avgVol = normalizedWeights.reduce((sum, w, i) => sum + w * vols[i], 0);

    let portfolioVol = avgVol;
    if (covarianceMatrix && covarianceMatrix.length === symbols.length) {
      const validIndices = symbols.map((s, i) => validSymbols.includes(s) ? i : -1).filter(i => i >= 0);
      try {
        let sum = 0;
        for (let i = 0; i < validIndices.length; i++) {
          for (let j = 0; j < validIndices.length; j++) {
            const vi = validIndices[i];
            const vj = validIndices[j];
            if (covarianceMatrix[vi] && covarianceMatrix[vi][vj] !== undefined) {
              sum += normalizedWeights[i] * normalizedWeights[j] * covarianceMatrix[vi][vj];
            }
          }
        }
        portfolioVol = Math.sqrt(Math.max(0, sum));
      } catch (e) {
        portfolioVol = avgVol;
      }
    }

    const portfolioSharpe = portfolioVol > 0 ? expectedReturn / portfolioVol : 0;

    const riskContributions = [];
    for (let i = 0; i < validSymbols.length; i++) {
      const contrib = normalizedWeights[i] * vols[i];
      riskContributions.push({
        symbol: validSymbols[i],
        weight: normalizedWeights[i],
        contribution: contrib / (avgVol * validSymbols.length || 1),
        volatility: vols[i],
        return: returns[i],
        sharpe: sharpes[i],
        maxDrawdown: drawdowns[i]
      });
    }

    const diversificationRatio = avgVol / (portfolioVol || 0.0001);

    const performancePath = generatePerformancePath(
      expectedReturn,
      portfolioVol,
      252,
      10000
    );

    const confidenceBand = {
      upper: performancePath.map((v, i) => v + Math.sqrt(i + 1) * portfolioVol * 1.645 * v / 100),
      lower: performancePath.map((v, i) => v - Math.sqrt(i + 1) * portfolioVol * 1.645 * v / 100)
    };

    const var95 = portfolioVol * 1.645;
    const cvar95 = portfolioVol * 2.06;

    return {
      expectedReturn,
      portfolioVol,
      portfolioSharpe,
      diversificationRatio,
      var95,
      cvar95,
      riskContributions,
      performancePath,
      confidenceBand,
      validSymbols,
      isServerCalc: false
    };
  }, [weights, riskData, symbols, covarianceMatrix, portfolioData]);

  function generatePerformancePath(expectedReturn, volatility, periods, initialValue) {
    const path = [initialValue];
    const dailyReturn = expectedReturn / periods;
    const dailyVol = volatility / Math.sqrt(periods);
    let value = initialValue;

    for (let i = 1; i <= periods; i++) {
      const randomShock = (Math.random() - 0.5) * 2 * dailyVol;
      value = value * (1 + dailyReturn + randomShock);
      path.push(value);
    }
    return path;
  }

  const chartOption = useMemo(() => {
    if (!portfolioMetrics) {
      return {
        backgroundColor: 'transparent',
        title: {
          text: '等待数据...',
          left: 'center',
          top: 'center',
          textStyle: { color: '#778da9', fontSize: 14 }
        }
      };
    }

    const { performancePath, confidenceBand } = portfolioMetrics;
    const xAxisData = performancePath.map((_, i) => i === 0 ? '0' : `D${i}`);

    const areaStyle = new echarts.graphic.LinearGradient(0, 0, 0, 1, [
      { offset: 0, color: 'rgba(0, 212, 255, 0.3)' },
      { offset: 1, color: 'rgba(0, 212, 255, 0.02)' }
    ]);

    const upperBand = confidenceBand.upper;
    const lowerBand = confidenceBand.lower;

    return {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(13, 27, 42, 0.95)',
        borderColor: '#415a77',
        textStyle: { color: '#e0e1dd', fontSize: 12 },
        formatter: (params) => {
          const date = params[0].axisValue;
          let html = `<strong>${date}</strong><br/>`;
          params.forEach(p => {
            if (p.seriesName === '组合净值' || p.seriesName === '预期路径') {
              html += `${p.marker}${p.seriesName}: <strong>${p.value.toFixed(2)}</strong><br/>`;
            }
          });
          return html;
        }
      },
      legend: {
        data: ['预期路径', '95%置信区间'],
        top: 0,
        right: 10,
        textStyle: { color: '#778da9', fontSize: 11 }
      },
      grid: {
        left: '3%',
        right: '3%',
        top: '12%',
        bottom: '8%',
        containLabel: true
      },
      xAxis: {
        type: 'category',
        data: xAxisData,
        axisLine: { lineStyle: { color: '#415a77' } },
        axisLabel: {
          color: '#778da9',
          fontSize: 10,
          interval: Math.floor(performancePath.length / 8)
        },
        splitLine: { show: false }
      },
      yAxis: {
        type: 'value',
        axisLine: { lineStyle: { color: '#415a77' } },
        axisLabel: {
          color: '#778da9',
          fontSize: 10,
          formatter: (v) => (v / 1000).toFixed(0) + 'K'
        },
        splitLine: {
          lineStyle: { color: 'rgba(65, 90, 119, 0.2)', type: 'dashed' }
        }
      },
      series: [
        {
          name: '95%置信上界',
          type: 'line',
          data: upperBand,
          lineStyle: { opacity: 0 },
          symbol: 'none',
          stack: 'confidence'
        },
        {
          name: '95%置信区间',
          type: 'line',
          data: lowerBand.map((v, i) => upperBand[i] - v),
          lineStyle: { opacity: 0 },
          symbol: 'none',
          areaStyle: {
            color: 'rgba(0, 212, 255, 0.1)'
          },
          stack: 'confidence'
        },
        {
          name: '预期路径',
          type: 'line',
          data: performancePath,
          smooth: true,
          symbol: 'none',
          lineStyle: {
            color: '#00d4ff',
            width: 2,
            shadowColor: 'rgba(0, 212, 255, 0.5)',
            shadowBlur: 10
          },
          areaStyle: areaStyle
        }
      ]
    };
  }, [portfolioMetrics]);

  const contributionOption = useMemo(() => {
    if (!portfolioMetrics || !portfolioMetrics.riskContributions) {
      return {
        backgroundColor: 'transparent'
      };
    }

    let data = [];
    const rc = portfolioMetrics.riskContributions;

    if (Array.isArray(rc)) {
      data = rc.slice().sort((a, b) => b.weight - a.weight).slice(0, 8);
    } else if (typeof rc === 'object') {
      data = Object.entries(rc)
        .map(([symbol, contribution]) => ({
          symbol,
          contribution: contribution,
          weight: weights[symbol] || 0,
          volatility: riskData[symbol]?.volatility || 0,
          return: riskData[symbol]?.annual_return || 0
        }))
        .sort((a, b) => b.weight - a.weight)
        .slice(0, 8);
    }

    return {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(13, 27, 42, 0.95)',
        borderColor: '#415a77',
        textStyle: { color: '#e0e1dd', fontSize: 12 },
        axisPointer: { type: 'shadow' },
        formatter: (params) => {
          const item = data[params[0].dataIndex];
          return `<strong>${item.symbol}</strong><br/>
                  权重: ${(item.weight * 100).toFixed(2)}%<br/>
                  波动率: ${(item.volatility * 100).toFixed(2)}%<br/>
                  预期收益: ${(item.return * 100).toFixed(2)}%`;
        }
      },
      grid: {
        left: '3%',
        right: '8%',
        top: '3%',
        bottom: '3%',
        containLabel: true
      },
      xAxis: {
        type: 'value',
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { show: false },
        splitLine: { show: false }
      },
      yAxis: {
        type: 'category',
        data: data.map(d => d.symbol),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: '#e0e1dd',
          fontSize: 11,
          fontWeight: 600
        },
        inverse: true
      },
      series: [
        {
          type: 'bar',
          data: data.map(d => (d.weight * 100).toFixed(2)),
          barWidth: '60%',
          itemStyle: {
            borderRadius: [0, 4, 4, 0],
            color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
              { offset: 0, color: '#00d4ff' },
              { offset: 1, color: '#00ff88' }
            ])
          },
          label: {
            show: true,
            position: 'right',
            color: '#e0e1dd',
            fontSize: 11,
            fontWeight: 600,
            formatter: '{c}%'
          }
        }
      ]
    };
  }, [portfolioMetrics, weights, riskData]);

  return (
    <div className="portfolio-chart">
      <div className="chart-main">
        <div className="chart-header">
          <div className="chart-title-row">
            <h3 className="chart-title">组合预期收益走势</h3>
            {portfolioMetrics && (
              <span className={`calc-badge ${portfolioMetrics.isServerCalc ? 'calc-badge--server' : 'calc-badge--local'}`}>
                {portfolioMetrics.isServerCalc ? '⚡ 精确计算' : '◐ 本地估算'}
              </span>
            )}
          </div>
          <div className="chart-subtitle">
            基于 {portfolioMetrics?.numAssets || portfolioMetrics?.validSymbols?.length || 0} 个资产的蒙特卡洛模拟
            {portfolioMetrics?.isServerCalc && ' · 数据来自 Python 量化引擎'}
          </div>
        </div>
        <ReactECharts
          ref={chartRef}
          option={chartOption}
          style={{ height: '280px', width: '100%' }}
          opts={{ renderer: 'canvas' }}
        />
      </div>

      <div className="chart-sidebar">
        <div className="metrics-grid">
          <div className="metric-card">
            <div className="metric-label">预期年化收益</div>
            <div className={`metric-value ${portfolioMetrics?.expectedReturn >= 0 ? 'positive' : 'negative'}`}>
              {portfolioMetrics ? (portfolioMetrics.expectedReturn * 100).toFixed(2) + '%' : '--'}
            </div>
          </div>
          <div className="metric-card">
            <div className="metric-label">组合波动率</div>
            <div className="metric-value warning">
              {portfolioMetrics ? (portfolioMetrics.portfolioVol * 100).toFixed(2) + '%' : '--'}
            </div>
          </div>
          <div className="metric-card">
            <div className="metric-label">夏普比率</div>
            <div className={`metric-value ${portfolioMetrics?.portfolioSharpe >= 1 ? 'positive' : 'warning'}`}>
              {portfolioMetrics ? portfolioMetrics.portfolioSharpe.toFixed(2) : '--'}
            </div>
          </div>
          <div className="metric-card">
            <div className="metric-label">分散化比率</div>
            <div className="metric-value info">
              {portfolioMetrics ? portfolioMetrics.diversificationRatio.toFixed(2) : '--'}
            </div>
          </div>
          <div className="metric-card">
            <div className="metric-label">VaR (95%)</div>
            <div className="metric-value negative">
              {portfolioMetrics ? (portfolioMetrics.var95 * 100).toFixed(2) + '%' : '--'}
            </div>
          </div>
          <div className="metric-card">
            <div className="metric-label">CVaR (95%)</div>
            <div className="metric-value negative">
              {portfolioMetrics ? (portfolioMetrics.cvar95 * 100).toFixed(2) + '%' : '--'}
            </div>
          </div>
        </div>
      </div>

      <div className="contribution-section">
        <h4 className="section-title">风险贡献分布</h4>
        <ReactECharts
          option={contributionOption}
          style={{ height: '180px', width: '100%' }}
          opts={{ renderer: 'canvas' }}
        />
      </div>
    </div>
  );
}

export default PortfolioChart;
