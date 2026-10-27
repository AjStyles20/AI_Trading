import { useEffect, useState } from 'react';
import Sidebar from './components/Sidebar';
import ChartPanel from './components/ChartPanel';
import BottomPanel from './components/BottomPanel';
import StrategyBuilder from './components/StrategyBuilder';
import type { AssetType, BacktestResults, BuilderGraph } from './components/BottomPanel';
import type { StrategyBuilderGraph } from './components/StrategyBuilder';
import { assetTypeFor, normalizeSymbol } from './lib/watchlist';
import { PREF_KEYS, readPreference, storePreference } from './lib/preferences';
import { isShortcutEvent, SHORTCUTS } from './lib/shortcuts';

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
  const [symbol, setSymbol] = useState(() => readPreference(PREF_KEYS.symbol, (value) => (typeof value === 'string' ? normalizeSymbol(value) : null), 'BTC/USDT'));
  const [assetType, setAssetType] = useState<AssetType>(() => assetTypeFor(symbol));
  const [showShortcuts, setShowShortcuts] = useState(false);

  useEffect(() => { storePreference(PREF_KEYS.symbol, symbol); }, [symbol]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setShowShortcuts(false);
        return;
      }
      if (event.key === '?' && isShortcutEvent(event)) {
        event.preventDefault();
        setShowShortcuts((open) => !open);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  const handleSymbolChange = (newSymbol: string) => {
    setSymbol(newSymbol);
    setAssetType(assetTypeFor(newSymbol));
  };

  return (
    <div className="flex h-screen w-full bg-[#0a0a0c] text-slate-300 font-sans overflow-hidden">
      {showShortcuts && (
        <div
          role="dialog"
          aria-label="Keyboard shortcuts"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
          onClick={() => setShowShortcuts(false)}
        >
          <div className="w-80 rounded-xl border border-[#2a2a35] bg-[#16161e] p-4" onClick={(event) => event.stopPropagation()}>
            <h2 className="mb-3 text-xs font-bold uppercase tracking-widest text-gray-400">Keyboard shortcuts</h2>
            <dl className="space-y-2 text-xs">
              {SHORTCUTS.map((shortcut) => (
                <div key={shortcut.keys} className="flex justify-between gap-4">
                  <dt className="font-mono text-[#a55eea]">{shortcut.keys}</dt>
                  <dd className="text-right text-gray-300">{shortcut.action}</dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      )}
      {/* Left Sidebar - AI Chat & Watchlist */}
      <Sidebar 
        activeView={activeView} 
        onViewChange={setActiveView} 
        currentSymbol={symbol}
        onSymbolChange={handleSymbolChange}
      />

      {/* Main Content Area */}
      <div className="flex flex-col flex-1 overflow-y-auto overscroll-contain scroll-smooth">
        {/* Top/Center Panel - Charts & Indicators / Strategy Builder.
            shrink-0 with a definite height: as flex items of the scroll
            container, both panels would otherwise be squeezed to their minimum
            heights, starving the chart and clipping the bottom panel. */}
        <div className="bg-[#121216] border-b border-[#2a2a35] p-0 flex flex-col relative w-full shrink-0 h-[max(480px,85vh)]">
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
        <div className="bg-[#0f0f13] p-4 flex flex-col shrink-0 min-h-[350px]">
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
                setAssetType(payload.assetType || assetTypeFor(payload.symbol));
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
