import { useState } from 'react';
import Sidebar from './components/Sidebar';
import ChartPanel from './components/ChartPanel';
import BottomPanel from './components/BottomPanel';
import StrategyBuilder from './components/StrategyBuilder';
import type { AssetType, BacktestResults, BuilderGraph } from './components/BottomPanel';
import type { StrategyBuilderGraph } from './components/StrategyBuilder';

export type ViewType = 'chart' | 'builder';

const DEFAULT_CODE = `# Astral AI Strategy Builder
# Type a prompt in the box above and click "Generate Strategy"
# Example: "Create a MACD + RSI Oversold strategy"

def strategy(df):
    # Your AI-generated strategy will appear here
    pass
`;

function App() {
  const [activeView, setActiveView] = useState<ViewType>('chart');
  const [strategyCode, setStrategyCode] = useState(DEFAULT_CODE);
  const [backtestResults, setBacktestResults] = useState<BacktestResults | null>(null);
  const [builderGraph, setBuilderGraph] = useState<StrategyBuilderGraph>({ nodes: [], edges: [] });
  const [symbol, setSymbol] = useState('BTC/USDT');
  const [assetType, setAssetType] = useState<AssetType>('crypto');

  const handleSymbolChange = (newSymbol: string) => {
    setSymbol(newSymbol);
    setAssetType(newSymbol.includes('/') || newSymbol.includes('-') ? 'crypto' : 'stock');
  };

  return (
    <div className="flex h-screen w-full bg-[#0a0a0c] text-slate-300 font-sans overflow-hidden">
      {/* Left Sidebar - AI Chat & Watchlist */}
      <Sidebar 
        activeView={activeView} 
        onViewChange={setActiveView} 
        currentSymbol={symbol}
        onSymbolChange={handleSymbolChange}
      />

      {/* Main Content Area */}
      <div className="flex flex-col flex-1 overflow-y-auto overscroll-contain scroll-smooth">
        {/* Top/Center Panel - Charts & Indicators / Strategy Builder */}
        <div className="bg-[#121216] border-b border-[#2a2a35] p-0 flex flex-col relative w-full min-h-[450px]">
          {activeView === 'chart' ? (
            <ChartPanel
              symbol={symbol}
              backtestResults={backtestResults ?? undefined}
            />
          ) : (
            <StrategyBuilder
              setStrategyCode={setStrategyCode}
              initialGraph={builderGraph}
              onGraphChange={setBuilderGraph}
            />
          )}
        </div>

        {/* Bottom Panel - Strategy Code & Backtest Results */}
        <div className="bg-[#0f0f13] p-4 flex flex-col min-h-[350px]">
          <BottomPanel 
            symbol={symbol}
            assetType={assetType}
            strategyCode={strategyCode} 
            setStrategyCode={setStrategyCode} 
            backtestResults={backtestResults} 
            setBacktestResults={setBacktestResults} 
            builderGraph={builderGraph as BuilderGraph}
            onLoadStrategy={(payload) => {
              setStrategyCode(payload.code);
              setBuilderGraph((payload.builderGraph as StrategyBuilderGraph) || { nodes: [], edges: [] });
              if (payload.symbol) {
                setSymbol(payload.symbol);
                setAssetType(payload.assetType || (payload.symbol.includes('/') || payload.symbol.includes('-') ? 'crypto' : 'stock'));
              }
              setActiveView('builder');
            }}
          />
        </div>
      </div>
    </div>
  );
}

export default App;
