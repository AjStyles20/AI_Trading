import { useState, useRef, useEffect } from 'react';
import axios from 'axios';

const BACKEND_URL = 'http://127.0.0.1:8000';

type Message = {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  timestamp: string;
};

const SUGGESTIONS = [
  "Analyze AAPL trend",
  "Create a MACD + RSI strategy",
  "Backtest a Bollinger breakout",
  "What's the best entry for BTC today?",
];

type SidebarProps = {
  activeView: 'chart' | 'builder';
  onViewChange: (view: 'chart' | 'builder') => void;
  currentSymbol: string;
  onSymbolChange: (symbol: string) => void;
};

export default function Sidebar({ 
  activeView, 
  onViewChange, 
  currentSymbol, 
  onSymbolChange 
}: SidebarProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '0',
      role: 'assistant',
      text: "Hello! I'm Astral AI, your intelligent trading companion. I can analyse markets, generate strategies, run backtests, and more. How can I help you today?",
      timestamp: new Date().toLocaleTimeString(),
    }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [backendOnline, setBackendOnline] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [openaiKey, setOpenaiKey] = useState('');
  const [tempKey, setTempKey] = useState('');
  const [binanceKey, setBinanceKey] = useState('');
  const [binanceSecret, setBinanceSecret] = useState('');
  const [binanceTestnetEnabled, setBinanceTestnetEnabled] = useState(false);
  const [binanceTestnetKey, setBinanceTestnetKey] = useState('');
  const [binanceTestnetSecret, setBinanceTestnetSecret] = useState('');
  const [bitgetKey, setBitgetKey] = useState('');
  const [bitgetSecret, setBitgetSecret] = useState('');
  const [bitgetPassphrase, setBitgetPassphrase] = useState('');
  const [bitgetDemoEnabled, setBitgetDemoEnabled] = useState(false);
  const [bitgetDemoKey, setBitgetDemoKey] = useState('');
  const [bitgetDemoSecret, setBitgetDemoSecret] = useState('');
  const [bitgetDemoPassphrase, setBitgetDemoPassphrase] = useState('');
  const [alpacaKey, setAlpacaKey] = useState('');
  const [alpacaSecret, setAlpacaSecret] = useState('');
  const [alpacaPaperKey, setAlpacaPaperKey] = useState('');
  const [alpacaPaperSecret, setAlpacaPaperSecret] = useState('');
  const [tempBinanceKey, setTempBinanceKey] = useState('');
  const [tempBinanceSecret, setTempBinanceSecret] = useState('');
  const [tempBinanceTestnetEnabled, setTempBinanceTestnetEnabled] = useState(false);
  const [tempBinanceTestnetKey, setTempBinanceTestnetKey] = useState('');
  const [tempBinanceTestnetSecret, setTempBinanceTestnetSecret] = useState('');
  const [tempBitgetKey, setTempBitgetKey] = useState('');
  const [tempBitgetSecret, setTempBitgetSecret] = useState('');
  const [tempBitgetPassphrase, setTempBitgetPassphrase] = useState('');
  const [tempBitgetDemoEnabled, setTempBitgetDemoEnabled] = useState(false);
  const [tempBitgetDemoKey, setTempBitgetDemoKey] = useState('');
  const [tempBitgetDemoSecret, setTempBitgetDemoSecret] = useState('');
  const [tempBitgetDemoPassphrase, setTempBitgetDemoPassphrase] = useState('');
  const [tempAlpacaKey, setTempAlpacaKey] = useState('');
  const [tempAlpacaSecret, setTempAlpacaSecret] = useState('');
  const [tempAlpacaPaperKey, setTempAlpacaPaperKey] = useState('');
  const [tempAlpacaPaperSecret, setTempAlpacaPaperSecret] = useState('');
  const [watchlist, setWatchlist] = useState(['BTC/USDT', 'ETH/USDT', 'AAPL', 'NVDA', 'TSLA', 'SOL-USD']);
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const messageEndRef = useRef<HTMLDivElement>(null);
  const hasOpenaiKey = Boolean(openaiKey && openaiKey !== 'mock-key');
 
  // Fetch settings on load
  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const res = await axios.get(`${BACKEND_URL}/api/settings`);
        setBackendOnline(true);
        if (res.data.api_keys?.openai) {
          setOpenaiKey(res.data.api_keys.openai);
          setTempKey(res.data.api_keys.openai);
        }
        if (res.data.api_keys?.binance_key) {
          setBinanceKey(res.data.api_keys.binance_key);
          setTempBinanceKey(res.data.api_keys.binance_key);
        }
        if (res.data.api_keys?.binance_secret) {
          setBinanceSecret(res.data.api_keys.binance_secret);
          setTempBinanceSecret(res.data.api_keys.binance_secret);
        }
        const testnetEnabled = ['1', 'true', 'yes', 'on'].includes(
          String(res.data.api_keys?.binance_testnet || '').trim().toLowerCase()
        );
        setBinanceTestnetEnabled(testnetEnabled);
        setTempBinanceTestnetEnabled(testnetEnabled);
        if (res.data.api_keys?.binance_testnet_key) {
          setBinanceTestnetKey(res.data.api_keys.binance_testnet_key);
          setTempBinanceTestnetKey(res.data.api_keys.binance_testnet_key);
        }
        if (res.data.api_keys?.binance_testnet_secret) {
          setBinanceTestnetSecret(res.data.api_keys.binance_testnet_secret);
          setTempBinanceTestnetSecret(res.data.api_keys.binance_testnet_secret);
        }
        if (res.data.api_keys?.bitget_key) {
          setBitgetKey(res.data.api_keys.bitget_key);
          setTempBitgetKey(res.data.api_keys.bitget_key);
        }
        if (res.data.api_keys?.bitget_secret) {
          setBitgetSecret(res.data.api_keys.bitget_secret);
          setTempBitgetSecret(res.data.api_keys.bitget_secret);
        }
        if (res.data.api_keys?.bitget_passphrase) {
          setBitgetPassphrase(res.data.api_keys.bitget_passphrase);
          setTempBitgetPassphrase(res.data.api_keys.bitget_passphrase);
        }
        const bitgetDemoEnabled = ['1', 'true', 'yes', 'on'].includes(
          String(res.data.api_keys?.bitget_demo || '').trim().toLowerCase()
        );
        setBitgetDemoEnabled(bitgetDemoEnabled);
        setTempBitgetDemoEnabled(bitgetDemoEnabled);
        if (res.data.api_keys?.bitget_demo_key) {
          setBitgetDemoKey(res.data.api_keys.bitget_demo_key);
          setTempBitgetDemoKey(res.data.api_keys.bitget_demo_key);
        }
        if (res.data.api_keys?.bitget_demo_secret) {
          setBitgetDemoSecret(res.data.api_keys.bitget_demo_secret);
          setTempBitgetDemoSecret(res.data.api_keys.bitget_demo_secret);
        }
        if (res.data.api_keys?.bitget_demo_passphrase) {
          setBitgetDemoPassphrase(res.data.api_keys.bitget_demo_passphrase);
          setTempBitgetDemoPassphrase(res.data.api_keys.bitget_demo_passphrase);
        }
        if (res.data.api_keys?.alpaca_key) {
          setAlpacaKey(res.data.api_keys.alpaca_key);
          setTempAlpacaKey(res.data.api_keys.alpaca_key);
        }
        if (res.data.api_keys?.alpaca_secret) {
          setAlpacaSecret(res.data.api_keys.alpaca_secret);
          setTempAlpacaSecret(res.data.api_keys.alpaca_secret);
        }
        if (res.data.api_keys?.alpaca_paper_key) {
          setAlpacaPaperKey(res.data.api_keys.alpaca_paper_key);
          setTempAlpacaPaperKey(res.data.api_keys.alpaca_paper_key);
        }
        if (res.data.api_keys?.alpaca_paper_secret) {
          setAlpacaPaperSecret(res.data.api_keys.alpaca_paper_secret);
          setTempAlpacaPaperSecret(res.data.api_keys.alpaca_paper_secret);
        }
      } catch {
        setBackendOnline(false);
      }
    };
    fetchSettings();
  }, []);

  const saveSettings = async () => {
    try {
      await axios.post(`${BACKEND_URL}/api/settings`, {
        api_keys: {
          openai: tempKey,
          binance_key: tempBinanceKey,
          binance_secret: tempBinanceSecret,
          binance_testnet: tempBinanceTestnetEnabled ? 'true' : 'false',
          binance_testnet_key: tempBinanceTestnetKey,
          binance_testnet_secret: tempBinanceTestnetSecret,
          bitget_key: tempBitgetKey,
          bitget_secret: tempBitgetSecret,
          bitget_passphrase: tempBitgetPassphrase,
          bitget_demo: tempBitgetDemoEnabled ? 'true' : 'false',
          bitget_demo_key: tempBitgetDemoKey,
          bitget_demo_secret: tempBitgetDemoSecret,
          bitget_demo_passphrase: tempBitgetDemoPassphrase,
          alpaca_key: tempAlpacaKey,
          alpaca_secret: tempAlpacaSecret,
          alpaca_paper_key: tempAlpacaPaperKey,
          alpaca_paper_secret: tempAlpacaPaperSecret,
        }
      });
      setOpenaiKey(tempKey);
      setBinanceKey(tempBinanceKey);
      setBinanceSecret(tempBinanceSecret);
      setBinanceTestnetEnabled(tempBinanceTestnetEnabled);
      setBinanceTestnetKey(tempBinanceTestnetKey);
      setBinanceTestnetSecret(tempBinanceTestnetSecret);
      setBitgetKey(tempBitgetKey);
      setBitgetSecret(tempBitgetSecret);
      setBitgetPassphrase(tempBitgetPassphrase);
      setBitgetDemoEnabled(tempBitgetDemoEnabled);
      setBitgetDemoKey(tempBitgetDemoKey);
      setBitgetDemoSecret(tempBitgetDemoSecret);
      setBitgetDemoPassphrase(tempBitgetDemoPassphrase);
      setAlpacaKey(tempAlpacaKey);
      setAlpacaSecret(tempAlpacaSecret);
      setAlpacaPaperKey(tempAlpacaPaperKey);
      setAlpacaPaperSecret(tempAlpacaPaperSecret);
      setIsSettingsOpen(false);
      
      // Notify user success
      const successMsg: Message = {
        id: Date.now().toString(),
        role: 'assistant',
        text: "✅ Settings saved successfully. The AI Assistant is now re-initialized with your new configuration.",
        timestamp: new Date().toLocaleTimeString(),
      };
      setMessages(prev => [...prev, successMsg]);
    } catch {
      alert("Failed to save settings. Ensure the backend is running.");
    }
  };

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messageEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = async (query: string) => {
    if (!query.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      text: query,
      timestamp: new Date().toLocaleTimeString(),
    };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const res = await axios.post(`${BACKEND_URL}/api/chat`, {
        query,
        conversation_id: 'main_session',
      }, {
        timeout: 180000 // 180s timeout for model downloads/API calls
      });

      const aiMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        text: res.data.response,
        timestamp: new Date().toLocaleTimeString(),
      };
      setMessages(prev => [...prev, aiMessage]);
    } catch (err: unknown) {
      let errorText = "Backend is offline. Start the Python server with: `python backend/main.py`";

      if (axios.isAxiosError(err) && err.code === 'ECONNABORTED') {
        errorText = "AI is taking too long to respond. This usually happens during the first run while downloading models. Please try again in 30 seconds.";
      } else if (axios.isAxiosError(err) && err.response) {
        const detail = err.response.data?.detail;
        if (err.response.status === 401 || (typeof detail === 'string' && detail.includes('API key'))) {
             errorText = "Error: Invalid or missing API key. Please click the settings button above and provide a valid OpenAI key.";
        } else {
             errorText = `AI Error: ${typeof detail === 'string' ? detail : "Unknown error"}`;
        }
      }

      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        text: errorText,
        timestamp: new Date().toLocaleTimeString(),
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }

  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') sendMessage(input);
  };

  const handleSearch = async () => {
    if (!searchQuery.trim() || isSearching) return;
    setIsSearching(true);
    try {
      const ticker = searchQuery.toUpperCase();
      // Simple validation or just add it
      if (!watchlist.includes(ticker)) {
        setWatchlist(prev => [...prev, ticker]);
      }
      onSymbolChange(ticker);
      setSearchQuery('');
    } catch {
      alert("Symbol not found or data error.");
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <div className="w-80 h-full bg-[#111115] border-r border-[#2a2a35] flex flex-col shadow-2xl z-20 relative">
      {/* Settings Overlay */}
      {isSettingsOpen && (
        <div className="absolute inset-0 z-30 bg-[#0a0a0c]/90 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#1c1c26] border border-[#a55eea]/30 rounded-2xl w-full p-5 shadow-2xl animate-in fade-in zoom-in duration-200 flex flex-col max-h-[85vh]">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <span className="text-[#a55eea]">⚙️</span> Settings
              </h3>
              <button onClick={() => setIsSettingsOpen(false)} className="text-gray-500 hover:text-white transition-colors">
                ✕
              </button>
            </div>
            
            <div className="space-y-4 text-xs overflow-y-auto pr-2 min-h-0">
              <div>
                <label className="block text-gray-400 mb-1.5 font-medium">OpenAI API Key</label>
                <input 
                  type="password"
                  value={tempKey}
                  onChange={(e) => setTempKey(e.target.value)}
                  placeholder="sk-..."
                  className="w-full bg-[#0a0a0c] border border-[#2a2a35] rounded-lg py-2 px-3 text-white focus:border-[#a55eea] outline-none transition-all"
                />
                <p className="text-[10px] text-gray-500 mt-2 leading-relaxed">
                  Keys are stored locally in <code className="text-[#a55eea]">astral.db</code>. 
                  They are never sent to our servers.
                </p>
              </div>

              <div>
                <label className="block text-gray-400 mb-1.5 font-medium">Binance API Key</label>
                <input
                  type="password"
                  value={tempBinanceKey}
                  onChange={(e) => setTempBinanceKey(e.target.value)}
                  placeholder="Binance key"
                  className="w-full bg-[#0a0a0c] border border-[#2a2a35] rounded-lg py-2 px-3 text-white focus:border-[#a55eea] outline-none transition-all"
                />
              </div>

              <div>
                <label className="block text-gray-400 mb-1.5 font-medium">Binance Secret</label>
                <input
                  type="password"
                  value={tempBinanceSecret}
                  onChange={(e) => setTempBinanceSecret(e.target.value)}
                  placeholder="Binance secret"
                  className="w-full bg-[#0a0a0c] border border-[#2a2a35] rounded-lg py-2 px-3 text-white focus:border-[#a55eea] outline-none transition-all"
                />
                <p className="text-[10px] text-gray-500 mt-2 leading-relaxed">
                  Add Binance credentials here to enable broker-backed crypto execution from the trading panel.
                </p>
              </div>

              <label className="flex items-center justify-between rounded-lg border border-[#2a2a35] bg-[#14141b] px-3 py-2 text-gray-300">
                <span className="text-[11px] font-medium">Use Binance Testnet</span>
                <input
                  type="checkbox"
                  checked={tempBinanceTestnetEnabled}
                  onChange={(e) => setTempBinanceTestnetEnabled(e.target.checked)}
                  className="h-4 w-4 accent-[#a55eea]"
                />
              </label>

              <div>
                <label className="block text-gray-400 mb-1.5 font-medium">Binance Testnet Key</label>
                <input
                  type="password"
                  value={tempBinanceTestnetKey}
                  onChange={(e) => setTempBinanceTestnetKey(e.target.value)}
                  placeholder="Binance testnet key"
                  className="w-full bg-[#0a0a0c] border border-[#2a2a35] rounded-lg py-2 px-3 text-white focus:border-[#a55eea] outline-none transition-all"
                />
              </div>

              <div>
                <label className="block text-gray-400 mb-1.5 font-medium">Binance Testnet Secret</label>
                <input
                  type="password"
                  value={tempBinanceTestnetSecret}
                  onChange={(e) => setTempBinanceTestnetSecret(e.target.value)}
                  placeholder="Binance testnet secret"
                  className="w-full bg-[#0a0a0c] border border-[#2a2a35] rounded-lg py-2 px-3 text-white focus:border-[#a55eea] outline-none transition-all"
                />
                <p className="text-[10px] text-gray-500 mt-2 leading-relaxed">
                  When testnet is enabled, Astral routes Binance live-mode requests to the Binance testnet base URL instead of production.
                </p>
              </div>

              <div className="border-t border-[#2a2a35] pt-4">
                <div className="text-[11px] font-semibold text-gray-300 mb-3">Bitget Broker</div>
                <div className="space-y-4">
                  <div>
                    <label className="block text-gray-400 mb-1.5 font-medium">Bitget API Key</label>
                    <input
                      type="password"
                      value={tempBitgetKey}
                      onChange={(e) => setTempBitgetKey(e.target.value)}
                      placeholder="Bitget key"
                      className="w-full bg-[#0a0a0c] border border-[#2a2a35] rounded-lg py-2 px-3 text-white focus:border-[#a55eea] outline-none transition-all"
                    />
                  </div>

                  <div>
                    <label className="block text-gray-400 mb-1.5 font-medium">Bitget Secret</label>
                    <input
                      type="password"
                      value={tempBitgetSecret}
                      onChange={(e) => setTempBitgetSecret(e.target.value)}
                      placeholder="Bitget secret"
                      className="w-full bg-[#0a0a0c] border border-[#2a2a35] rounded-lg py-2 px-3 text-white focus:border-[#a55eea] outline-none transition-all"
                    />
                  </div>

                  <div>
                    <label className="block text-gray-400 mb-1.5 font-medium">Bitget Passphrase</label>
                    <input
                      type="password"
                      value={tempBitgetPassphrase}
                      onChange={(e) => setTempBitgetPassphrase(e.target.value)}
                      placeholder="Bitget passphrase"
                      className="w-full bg-[#0a0a0c] border border-[#2a2a35] rounded-lg py-2 px-3 text-white focus:border-[#a55eea] outline-none transition-all"
                    />
                    <p className="text-[10px] text-gray-500 mt-2 leading-relaxed">
                      Add Bitget credentials to enable broker-backed crypto execution. A passphrase is required for Bitget API access.
                    </p>
                  </div>

                  <label className="flex items-center justify-between rounded-lg border border-[#2a2a35] bg-[#14141b] px-3 py-2 text-gray-300">
                    <span className="text-[11px] font-medium">Use Bitget Demo Trading</span>
                    <input
                      type="checkbox"
                      checked={tempBitgetDemoEnabled}
                      onChange={(e) => setTempBitgetDemoEnabled(e.target.checked)}
                      className="h-4 w-4 accent-[#a55eea]"
                    />
                  </label>

                  <div>
                    <label className="block text-gray-400 mb-1.5 font-medium">Bitget Demo Key</label>
                    <input
                      type="password"
                      value={tempBitgetDemoKey}
                      onChange={(e) => setTempBitgetDemoKey(e.target.value)}
                      placeholder="Bitget demo key"
                      className="w-full bg-[#0a0a0c] border border-[#2a2a35] rounded-lg py-2 px-3 text-white focus:border-[#a55eea] outline-none transition-all"
                    />
                  </div>

                  <div>
                    <label className="block text-gray-400 mb-1.5 font-medium">Bitget Demo Secret</label>
                    <input
                      type="password"
                      value={tempBitgetDemoSecret}
                      onChange={(e) => setTempBitgetDemoSecret(e.target.value)}
                      placeholder="Bitget demo secret"
                      className="w-full bg-[#0a0a0c] border border-[#2a2a35] rounded-lg py-2 px-3 text-white focus:border-[#a55eea] outline-none transition-all"
                    />
                  </div>

                  <div>
                    <label className="block text-gray-400 mb-1.5 font-medium">Bitget Demo Passphrase</label>
                    <input
                      type="password"
                      value={tempBitgetDemoPassphrase}
                      onChange={(e) => setTempBitgetDemoPassphrase(e.target.value)}
                      placeholder="Bitget demo passphrase"
                      className="w-full bg-[#0a0a0c] border border-[#2a2a35] rounded-lg py-2 px-3 text-white focus:border-[#a55eea] outline-none transition-all"
                    />
                    <p className="text-[10px] text-gray-500 mt-2 leading-relaxed">
                      When demo trading is enabled, live Bitget executions are routed to the demo environment instead.
                    </p>
                  </div>
                </div>
              </div>

              <div className="border-t border-[#2a2a35] pt-4">
                <div className="text-[11px] font-semibold text-gray-300 mb-3">Alpaca Broker</div>
                <div className="space-y-4">
                  <div>
                    <label className="block text-gray-400 mb-1.5 font-medium">Alpaca Live Key</label>
                    <input
                      type="password"
                      value={tempAlpacaKey}
                      onChange={(e) => setTempAlpacaKey(e.target.value)}
                      placeholder="Alpaca live key"
                      className="w-full bg-[#0a0a0c] border border-[#2a2a35] rounded-lg py-2 px-3 text-white focus:border-[#a55eea] outline-none transition-all"
                    />
                  </div>

                  <div>
                    <label className="block text-gray-400 mb-1.5 font-medium">Alpaca Live Secret</label>
                    <input
                      type="password"
                      value={tempAlpacaSecret}
                      onChange={(e) => setTempAlpacaSecret(e.target.value)}
                      placeholder="Alpaca live secret"
                      className="w-full bg-[#0a0a0c] border border-[#2a2a35] rounded-lg py-2 px-3 text-white focus:border-[#a55eea] outline-none transition-all"
                    />
                  </div>

                  <div>
                    <label className="block text-gray-400 mb-1.5 font-medium">Alpaca Paper Key</label>
                    <input
                      type="password"
                      value={tempAlpacaPaperKey}
                      onChange={(e) => setTempAlpacaPaperKey(e.target.value)}
                      placeholder="Alpaca paper key"
                      className="w-full bg-[#0a0a0c] border border-[#2a2a35] rounded-lg py-2 px-3 text-white focus:border-[#a55eea] outline-none transition-all"
                    />
                  </div>

                  <div>
                    <label className="block text-gray-400 mb-1.5 font-medium">Alpaca Paper Secret</label>
                    <input
                      type="password"
                      value={tempAlpacaPaperSecret}
                      onChange={(e) => setTempAlpacaPaperSecret(e.target.value)}
                      placeholder="Alpaca paper secret"
                      className="w-full bg-[#0a0a0c] border border-[#2a2a35] rounded-lg py-2 px-3 text-white focus:border-[#a55eea] outline-none transition-all"
                    />
                    <p className="text-[10px] text-gray-500 mt-2 leading-relaxed">
                      Alpaca paper mode uses the paper endpoint. If paper keys are omitted, Astral falls back to the live Alpaca credentials.
                    </p>
                  </div>
                </div>
              </div>

              <div className="pt-2">
                <button 
                  onClick={saveSettings}
                  className="w-full bg-[#a55eea] hover:bg-[#b87ef7] text-white font-bold py-2.5 rounded-lg transition-all shadow-lg active:scale-[0.98]"
                >
                  Save Configuration
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="p-4 border-b border-[#2a2a35] flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#a55eea] to-[#6c5ce7] flex items-center justify-center shadow-lg">
             <span className="text-white font-black text-xs">A</span>
          </div>
          <div>
            <h1 className="text-base font-bold text-white tracking-wide">Astral<span className="text-[#a55eea]">AI</span></h1>
            <p className="text-[10px] text-gray-500 mt-0.5">Trading Companion</p>
          </div>
        </div>
        
        <div className="flex items-center gap-3">
           <button 
             onClick={() => {
               setTempKey(openaiKey);
               setTempBinanceKey(binanceKey);
               setTempBinanceSecret(binanceSecret);
               setTempBinanceTestnetEnabled(binanceTestnetEnabled);
               setTempBinanceTestnetKey(binanceTestnetKey);
               setTempBinanceTestnetSecret(binanceTestnetSecret);
               setTempBitgetKey(bitgetKey);
               setTempBitgetSecret(bitgetSecret);
               setTempBitgetPassphrase(bitgetPassphrase);
               setTempBitgetDemoEnabled(bitgetDemoEnabled);
               setTempBitgetDemoKey(bitgetDemoKey);
               setTempBitgetDemoSecret(bitgetDemoSecret);
               setTempBitgetDemoPassphrase(bitgetDemoPassphrase);
               setTempAlpacaKey(alpacaKey);
               setTempAlpacaSecret(alpacaSecret);
               setTempAlpacaPaperKey(alpacaPaperKey);
               setTempAlpacaPaperSecret(alpacaPaperSecret);
               setIsSettingsOpen(true);
             }}
             className="text-gray-500 hover:text-[#a55eea] transition-colors p-1"
             title="Settings"
           >
             <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.1a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>
           </button>
            <div className="flex items-center gap-2">
              <span
                className={`text-[9px] uppercase tracking-widest px-2 py-0.5 rounded-full border ${
                  hasOpenaiKey
                    ? 'border-emerald-400/50 text-emerald-300'
                    : 'border-amber-400/40 text-amber-300'
                }`}
                title={hasOpenaiKey ? 'OpenAI key detected' : 'Add an OpenAI key to enable AI features'}
              >
                {hasOpenaiKey ? 'AI Ready' : 'AI Key Needed'}
              </span>
              <div
                className={`w-2 h-2 rounded-full ${
                  backendOnline
                    ? 'bg-green-400 shadow-[0_0_6px_rgba(74,222,128,0.8)]'
                    : 'bg-yellow-500 shadow-[0_0_6px_rgba(234,179,8,0.8)]'
                }`}
                title={backendOnline ? 'Online' : 'Offline'}
              ></div>
            </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex p-2 gap-1 bg-[#1c1c24]/50 border-b border-[#2a2a35] flex-shrink-0">
        <button 
          onClick={() => onViewChange('chart')}
          className={`flex-1 py-1.5 text-[10px] font-bold rounded transition-all ${activeView === 'chart' ? 'bg-[#a55eea] text-white' : 'text-gray-500 hover:text-gray-300'}`}
        >
          DASHBOARD
        </button>
        <button 
          onClick={() => onViewChange('builder')}
          className={`flex-1 py-1.5 text-[10px] font-bold rounded transition-all ${activeView === 'builder' ? 'bg-[#6c5ce7] text-white' : 'text-gray-500 hover:text-gray-300'}`}
        >
          STRATEGY BUILDER
        </button>
      </div>

      {/* Watchlist Section */}
      <div className="flex flex-col border-b border-[#2a2a35] flex-shrink-0 transition-all">
        <div className="px-4 py-3 flex items-center justify-between">
          <h3 className="text-[10px] font-bold text-gray-500 uppercase tracking-widest">Watchlist</h3>
          <span className="text-[9px] text-gray-600 font-mono">{watchlist.length} Assets</span>
        </div>
        
        <div className="px-3 pb-3">
          <div className="relative group">
            <input 
              type="text"
              placeholder="Search ticker (e.g. GOOG, SOL-USD)..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              className="w-full bg-[#0a0a0c] border border-[#2a2a35] rounded-lg py-1.5 pl-8 pr-3 text-[10px] text-white focus:border-[#a55eea] outline-none transition-all"
            />
            <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500 group-focus-within:text-[#a55eea] transition-colors">
              {isSearching ? <div className="w-3 h-3 border border-[#a55eea] border-t-transparent rounded-full animate-spin"></div> : "🔍"}
            </span>
          </div>
        </div>

        <div className="flex flex-wrap gap-1 px-3 pb-3 max-h-32 overflow-y-auto custom-scrollbar">
          {watchlist.map((symbol) => (
            <button
              key={symbol}
              onClick={() => onSymbolChange(symbol)}
              className={`px-2.5 py-1 text-[10px] font-bold rounded-md border transition-all ${
                currentSymbol === symbol 
                  ? 'bg-[#a55eea]/10 border-[#a55eea] text-[#a55eea]' 
                  : 'bg-[#1c1c24] border-[#2a2a35] text-gray-400 hover:border-gray-500'
              }`}
            >
              {symbol}
            </button>
          ))}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {messages.map((msg) => (
          <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[90%] rounded-xl px-3 py-2 text-sm leading-relaxed shadow-md ${
              msg.role === 'user' 
                ? 'bg-[#a55eea] text-white rounded-br-sm'
                : 'bg-[#1c1c26] text-gray-200 border border-[#2a2a35] rounded-bl-sm'
            }`}>
              {msg.role === 'assistant' && (
                <div className="flex items-center gap-1.5 mb-1.5">
                  <div className="w-3.5 h-3.5 rounded-full bg-[#a55eea] flex items-center justify-center">
                    <span className="text-[7px] text-white font-bold">A</span>
                  </div>
                  <span className="text-[10px] text-[#a55eea] font-semibold">Astral AI</span>
                </div>
              )}
              <span className="whitespace-pre-wrap">{msg.text}</span>
              <div className={`text-[9px] mt-1 ${msg.role === 'user' ? 'text-purple-200' : 'text-gray-500'}`}>{msg.timestamp}</div>
            </div>
          </div>
        ))}

        {/* Typing indicator */}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-[#1c1c26] border border-[#2a2a35] rounded-xl rounded-bl-sm px-4 py-3">
              <div className="flex gap-1.5 items-center">
                {[0, 1, 2].map(i => (
                  <div key={i} className="w-1.5 h-1.5 bg-[#a55eea] rounded-full animate-bounce" style={{ animationDelay: `${i * 0.15}s` }}></div>
                ))}
              </div>
            </div>
          </div>
        )}
        <div ref={messageEndRef} />
      </div>

      {/* Quick Suggestions */}
      {messages.length < 2 && !isLoading && (
        <div className="px-3 pb-2 space-y-1.5 flex-shrink-0">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => sendMessage(s)}
              className="w-full text-left text-xs text-gray-400 px-3 py-2 rounded-lg border border-[#2a2a35] bg-[#1a1a22] hover:border-[#a55eea] hover:text-[#a55eea] transition-all"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <div className="p-3 border-t border-[#2a2a35] bg-[#0d0d12] flex-shrink-0">
        <div className="relative flex items-center gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            placeholder={openaiKey ? "Ask AI to analyze or trade..." : "Please configure API key in settings ⚙️"}
            className="flex-1 bg-[#1c1c24] text-sm text-white rounded-lg border border-[#2a2a35] focus:border-[#a55eea] focus:ring-1 focus:ring-[#a55eea] outline-none py-2.5 pl-3 pr-3 transition-all disabled:opacity-50"
          />
          <button
            onClick={() => sendMessage(input)}
            disabled={isLoading || !input.trim() || !openaiKey}
            className="w-9 h-9 rounded-lg bg-[#a55eea] flex items-center justify-center text-white hover:bg-[#b87ef7] transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex-shrink-0"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="m22 2-7 20-4-9-9-4Z"/>
              <path d="M22 2 11 13"/>
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
