import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';

const BACKEND_URL = 'http://127.0.0.1:8000';

export type AssetType = 'crypto' | 'stock';

export type BuilderGraph = {
  nodes: unknown[];
  edges: unknown[];
};

type ValidationResult = {
  valid?: boolean;
  errors?: string[];
  warnings?: string[];
  stats?: {
    rows: number;
    trade_signal_count: number;
    signal_values: Array<string | number>;
  };
};

type PerformanceMetrics = {
  total_return_pct: number;
  max_drawdown_pct: number;
  win_rate_pct: number;
};

type OptimizationCandidate = {
  score: number;
  code: string;
  params: Record<string, string | number>;
  metrics: PerformanceMetrics;
};

type OptimizationRun = {
  id?: number;
  label?: string;
  timestamp?: string;
  scenario?: {
    period?: string;
    interval?: string;
    fee_pct?: number;
    slippage_pct?: number;
  };
  best: OptimizationCandidate;
  results: OptimizationCandidate[];
};

type StrategyWorkspace = {
  id: number;
  name: string;
  code: string;
  symbol?: string;
  asset_type?: AssetType;
  tags?: string[];
  builder_graph?: BuilderGraph;
  validation_summary?: ValidationResult;
  optimization_summary?: Partial<OptimizationCandidate>;
  is_baseline?: boolean;
  is_archived?: boolean;
  last_modified?: string;
};

export type TradeRecord = {
  id?: number;
  symbol?: string;
  side?: string;
  qty?: number;
  type?: string;
  price: number;
  balance?: number;
  broker_id?: string;
  execution_mode?: string;
  order_status?: string;
  order_type?: string;
  broker_order_id?: string | null;
  is_test?: boolean;
  metadata?: Record<string, unknown>;
  timestamp: string;
};

type BrokerDescriptor = {
  broker_id: string;
  display_name: string;
  supports_live: boolean;
  supported_asset_types: string[];
  configured: boolean;
  environment?: string;
};

type BrokerAccountSummary = {
  broker_id: string;
  display_name: string;
  execution_mode: string;
  environment?: string;
  configured: boolean;
  can_trade: boolean;
  balances: Array<{
    asset: string;
    free: number;
    locked: number;
  }>;
  warnings: string[];
};

type TradingPreflightResponse = {
  broker: BrokerDescriptor;
  account: BrokerAccountSummary;
  validation: {
    ok: boolean;
    warnings: string[];
    normalized_qty?: number;
    original_qty?: number;
    estimated_notional?: number;
  };
  market_price?: number;
};

type TradingTestOrderResponse = {
  ok: boolean;
  broker_id: string;
  execution_mode: string;
  message: string;
  environment?: string;
  validation: {
    ok: boolean;
    warnings: string[];
    normalized_qty?: number;
    original_qty?: number;
    estimated_notional?: number;
  };
  market_price?: number;
};

type BrokerOpenOrder = {
  broker_order_id?: string | null;
  symbol: string;
  side: string;
  status: string;
  type: string;
  orig_qty: number;
  executed_qty: number;
  price: number;
  time: number;
};

type BrokerPosition = {
  symbol: string;
  qty: number;
  available_qty: number;
  locked_qty: number;
  market_value: number | null;
  avg_entry_price: number | null;
  unrealized_pl: number | null;
  side: string;
};

type BrokerPortfolioSnapshot = {
  positions: BrokerPosition[];
  openOrders: BrokerOpenOrder[];
};

export type BacktestResults = {
  total_return_pct?: number;
  max_drawdown_pct?: number;
  trade_count?: number;
  final_equity?: number;
  buy_hold_return_pct?: number;
  win_rate_pct?: number;
  equity_curve?: number[];
  validation?: ValidationResult | null;
  scenario?: {
    period?: string;
    interval?: string;
    fee_pct?: number;
    slippage_pct?: number;
  };
  trade_history?: TradeRecord[];
};

const TAG_ALIAS_MAP: Record<string, string> = {
  'mean reversion': 'mean-reversion',
  mean_reversion: 'mean-reversion',
  'trend following': 'trend-following',
  trend_following: 'trend-following',
};

const normalizeTags = (tags: string[]): string[] => {
  const normalized = tags
    .map((tag) => TAG_ALIAS_MAP[tag.trim().toLowerCase()] || tag.trim().toLowerCase())
    .filter(Boolean);

  return Array.from(new Set(normalized));
};

export default function BottomPanel({
  symbol,
  assetType,
  strategyCode,
  setStrategyCode,
  backtestResults,
  setBacktestResults,
  builderGraph,
  onLoadStrategy,
}: {
  symbol: string,
  assetType: AssetType,
  strategyCode: string,
  setStrategyCode: (c: string) => void,
  backtestResults: BacktestResults | null,
  setBacktestResults: (r: BacktestResults | null) => void,
  builderGraph: BuilderGraph,
  onLoadStrategy: (payload: { code: string; builderGraph?: BuilderGraph; symbol?: string; assetType?: AssetType }) => void,
}) {
  const [activeTab, setActiveTab] = useState('code');
  const [strategyPrompt, setStrategyPrompt] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [isBacktesting, setIsBacktesting] = useState(false);
  const [isLiveTrading, setIsLiveTrading] = useState(false);
  const [tradingLogs, setTradingLogs] = useState<string[]>([]);
  const [tradeHistory, setTradeHistory] = useState<TradeRecord[]>([]);
  const [isRefreshingTradeHistory, setIsRefreshingTradeHistory] = useState(false);
  const [isCancellingTradeId, setIsCancellingTradeId] = useState<number | null>(null);
  const [tradeHistoryFilter, setTradeHistoryFilter] = useState<'all' | 'filled' | 'tests' | 'issues' | 'open'>('all');
  const [brokerOpenOrders, setBrokerOpenOrders] = useState<BrokerOpenOrder[]>([]);
  const [isRefreshingOpenOrders, setIsRefreshingOpenOrders] = useState(false);
  const [brokerPositions, setBrokerPositions] = useState<BrokerPosition[]>([]);
  const [isRefreshingPositions, setIsRefreshingPositions] = useState(false);
  const [brokerPortfolioSnapshot, setBrokerPortfolioSnapshot] = useState<BrokerPortfolioSnapshot>({ positions: [], openOrders: [] });
  const [availableBrokers, setAvailableBrokers] = useState<BrokerDescriptor[]>([]);
  const [selectedBrokerId, setSelectedBrokerId] = useState('paper');
  const [executionMode, setExecutionMode] = useState<'paper' | 'live'>('paper');
  const [settingsApiKeys, setSettingsApiKeys] = useState<Record<string, string>>({});
  const [binanceEnvironment, setBinanceEnvironment] = useState<'live' | 'testnet'>('live');
  const [bitgetEnvironment, setBitgetEnvironment] = useState<'live' | 'demo'>('live');
  const [isEnvironmentUpdating, setIsEnvironmentUpdating] = useState(false);
  const [strategySummary, setStrategySummary] = useState('');
  const [backtestSummary, setBacktestSummary] = useState('');
  const [isSummarizingStrategy, setIsSummarizingStrategy] = useState(false);
  const [isSummarizingBacktest, setIsSummarizingBacktest] = useState(false);
  const [brokerAccountSummary, setBrokerAccountSummary] = useState<BrokerAccountSummary | null>(null);
  const [isTestingOrder, setIsTestingOrder] = useState(false);
  const [optimizationResults, setOptimizationResults] = useState<OptimizationRun | null>(null);
  const [optimizationHistory, setOptimizationHistory] = useState<OptimizationRun[]>([]);
  const [isOptimizing, setIsOptimizing] = useState(false);
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [savedStrategies, setSavedStrategies] = useState<StrategyWorkspace[]>([]);
  const [selectedStrategyIds, setSelectedStrategyIds] = useState<number[]>([]);
  const [compareLeftId, setCompareLeftId] = useState<number | null>(null);
  const [compareRightId, setCompareRightId] = useState<number | null>(null);
  const [strategyCollection, setStrategyCollection] = useState<'active' | 'archived' | 'all'>('active');
  const [strategySearch, setStrategySearch] = useState('');
  const [strategyFilter, setStrategyFilter] = useState<'all' | 'baseline' | 'validated' | 'issues'>('all');
  const [strategySort, setStrategySort] = useState<'updated' | 'name' | 'symbol'>('updated');
  const [selectedTagFilters, setSelectedTagFilters] = useState<string[]>([]);
  const [strategyViewMode, setStrategyViewMode] = useState<'flat' | 'grouped'>('flat');
  const [isSaveModalOpen, setIsSaveModalOpen] = useState(false);
  const [strategyName, setStrategyName] = useState('');
  const [strategyTagsInput, setStrategyTagsInput] = useState('');
  const [savedStrategyId, setSavedStrategyId] = useState<number | null>(null);
  const [isSavingStrategy, setIsSavingStrategy] = useState(false);
  const [optimizerType, setOptimizerType] = useState('ema_rsi');
  const [optimizerRanges, setOptimizerRanges] = useState<Record<string, string>>({
    ema_fast: '8,12,21',
    ema_slow: '26,34,55',
    rsi_period: '10,14',
    rsi_buy: '25,30,35',
    rsi_sell: '65,70,75',
    sma_fast: '5,10,20',
    sma_slow: '30,50,100',
    stop_loss_pct: '2,3,5',
    take_profit_pct: '4,6,8',
    cooldown_bars: '0,2,4',
    position_size_pct: '25,50,100',
  });
  const [backtestInterval, setBacktestInterval] = useState('1h');
  const [backtestPeriod, setBacktestPeriod] = useState('6mo');
  const [initialBalance, setInitialBalance] = useState(10000);
  const [feePct, setFeePct] = useState(0.1);
  const [slippagePct, setSlippagePct] = useState(0.05);

  const tagPresets = ['crypto', 'stocks', 'swing', 'scalp', 'trend', 'mean-reversion', 'breakout'];

  const fetchTradingStatus = async () => {
    try {
      const res = await axios.get(`${BACKEND_URL}/api/trading/status`);
      setIsLiveTrading(res.data.is_active);
      setTradingLogs(res.data.logs);
      setSelectedBrokerId(res.data.config?.broker_id || 'paper');
      setExecutionMode(res.data.config?.execution_mode || 'paper');
    } catch (err) {
      console.error('Failed to fetch trading status:', err);
    }
  };

  const fetchTradeHistory = useCallback(async (refreshStatuses = false) => {
    try {
      if (refreshStatuses) {
        setIsRefreshingTradeHistory(true);
      }
      const endpoint = refreshStatuses
        ? `${BACKEND_URL}/api/trading/history/refresh`
        : `${BACKEND_URL}/api/trading/history`;
      const historyRes = await axios.get<TradeRecord[]>(endpoint);
      setTradeHistory(historyRes.data);
    } catch (err) {
      console.error('Failed to fetch trading history:', err);
    } finally {
      if (refreshStatuses) {
        setIsRefreshingTradeHistory(false);
      }
    }
  }, []);

  const fetchOpenOrders = useCallback(async () => {
    try {
      setIsRefreshingOpenOrders(true);
      if (executionMode !== 'live') {
        setBrokerOpenOrders([]);
        return;
      }
      const res = await axios.get<{ items: BrokerOpenOrder[] }>(`${BACKEND_URL}/api/trading/open-orders`, {
        params: {
          symbol,
          asset_type: assetType,
          broker_id: selectedBrokerId,
          execution_mode: executionMode,
        },
      });
      setBrokerOpenOrders(res.data.items || []);
    } catch (err) {
      console.error('Failed to fetch broker open orders:', err);
      setBrokerOpenOrders([]);
    } finally {
      setIsRefreshingOpenOrders(false);
    }
  }, [assetType, executionMode, selectedBrokerId, symbol]);

  const fetchBrokerPositions = useCallback(async () => {
    try {
      setIsRefreshingPositions(true);
      const res = await axios.get<{ items: BrokerPosition[] }>(`${BACKEND_URL}/api/trading/positions`, {
        params: {
          symbol,
          asset_type: assetType,
          broker_id: selectedBrokerId,
          execution_mode: executionMode,
        },
      });
      setBrokerPositions(res.data.items || []);
    } catch (err) {
      console.error('Failed to fetch broker positions:', err);
      setBrokerPositions([]);
    } finally {
      setIsRefreshingPositions(false);
    }
  }, [assetType, executionMode, selectedBrokerId, symbol]);

  const fetchBrokerPortfolioSnapshot = useCallback(async () => {
    try {
      const [positionsRes, ordersRes] = await Promise.all([
        axios.get<{ items: BrokerPosition[] }>(`${BACKEND_URL}/api/trading/positions`, {
          params: {
            symbol: '',
            asset_type: assetType,
            broker_id: selectedBrokerId,
            execution_mode: executionMode,
          },
        }),
        axios.get<{ items: BrokerOpenOrder[] }>(`${BACKEND_URL}/api/trading/open-orders`, {
          params: {
            symbol: '',
            asset_type: assetType,
            broker_id: selectedBrokerId,
            execution_mode: executionMode,
          },
        }),
      ]);
      setBrokerPortfolioSnapshot({
        positions: positionsRes.data.items || [],
        openOrders: ordersRes.data.items || [],
      });
    } catch (err) {
      console.error('Failed to fetch broker portfolio snapshot:', err);
      setBrokerPortfolioSnapshot({ positions: [], openOrders: [] });
    }
  }, [assetType, executionMode, selectedBrokerId]);

  useEffect(() => {
    void fetchTradingStatus();
    void fetchTradeHistory();
    void fetchOpenOrders();
    void fetchBrokerPositions();
    void fetchBrokerPortfolioSnapshot();
    const timer = setInterval(() => {
      void fetchTradingStatus();
      void fetchTradeHistory(executionMode === 'live');
      void fetchOpenOrders();
      void fetchBrokerPositions();
      void fetchBrokerPortfolioSnapshot();
    }, 5000);
    return () => clearInterval(timer);
  }, [executionMode, fetchBrokerPortfolioSnapshot, fetchBrokerPositions, fetchOpenOrders, fetchTradeHistory]);

  const fetchSettings = useCallback(async () => {
    try {
      const res = await axios.get(`${BACKEND_URL}/api/settings`);
      const apiKeys = res.data.api_keys || {};
      setSettingsApiKeys(apiKeys);
      const binanceEnv = ['1', 'true', 'yes', 'on'].includes(
        String(apiKeys.binance_testnet || '').trim().toLowerCase()
      )
        ? 'testnet'
        : 'live';
      setBinanceEnvironment(binanceEnv);
      const bitgetEnv = ['1', 'true', 'yes', 'on'].includes(
        String(apiKeys.bitget_demo || '').trim().toLowerCase()
      )
        ? 'demo'
        : 'live';
      setBitgetEnvironment(bitgetEnv);
    } catch (err) {
      console.error('Failed to fetch settings:', err);
    }
  }, []);

  useEffect(() => {
    void fetchSettings();
  }, [fetchSettings]);

  const fetchBrokers = useCallback(async () => {
    try {
      const res = await axios.get(`${BACKEND_URL}/api/trading/brokers`);
      setAvailableBrokers(res.data.items || []);
    } catch (err) {
      console.error('Failed to fetch brokers:', err);
    }
  }, []);

  useEffect(() => {
    void fetchBrokers();
  }, [fetchBrokers]);

  const fetchBrokerAccount = useCallback(async () => {
    try {
      const res = await axios.get(`${BACKEND_URL}/api/trading/account/${selectedBrokerId}`, {
        params: { execution_mode: executionMode },
      });
      setBrokerAccountSummary(res.data);
    } catch (err) {
      console.error('Failed to fetch broker account summary:', err);
      setBrokerAccountSummary(null);
    }
  }, [executionMode, selectedBrokerId]);

  useEffect(() => {
    void fetchBrokerAccount();
  }, [fetchBrokerAccount]);

  const fetchSavedStrategies = useCallback(async () => {
    try {
      const res = await axios.get(`${BACKEND_URL}/api/strategies`, {
        params: {
          include_archived: strategyCollection === 'all',
          archived_only: strategyCollection === 'archived',
        },
      });
      const items: StrategyWorkspace[] = res.data.items || [];
      setSavedStrategies(items);
      setSelectedStrategyIds((current) => current.filter((id) => items.some((strategy) => strategy.id === id)));
    } catch (err) {
      console.error('Failed to fetch saved strategies:', err);
    }
  }, [strategyCollection]);

  useEffect(() => {
    void fetchSavedStrategies();
  }, [fetchSavedStrategies]);

  const generateStrategy = async () => {
    if (!strategyPrompt.trim() || isGenerating) return;
    setIsGenerating(true);
    setActiveTab('code');
    setStrategySummary('');
    setStrategyCode('# Generating strategy with Astral AI...\n# Please wait...');
    try {
      const res = await axios.post(`${BACKEND_URL}/api/strategy`, { prompt: strategyPrompt });
      setStrategyCode(res.data.code || '# No code returned.');
    } catch {
      setStrategyCode('# Backend offline. Start the Python server:\n# python backend/main.py');
    } finally {
      setIsGenerating(false);
    }
  };

  const runBacktest = async () => {
    if (isBacktesting) return;
    setIsBacktesting(true);
    setActiveTab('backtest');
    setBacktestSummary('');
    try {
      const res = await axios.post(`${BACKEND_URL}/api/backtest/run`, {
        symbol,
        asset_type: assetType,
        interval: backtestInterval,
        period: backtestPeriod,
        initial_balance: initialBalance,
        fee_pct: feePct,
        slippage_pct: slippagePct,
        strategy_code: strategyCode,
      });
      setBacktestResults(res.data);
      setValidationResult(res.data.validation || null);
    } catch (err) {
      console.error(err);
      alert('Backtest failed. Ensure the strategy code is valid Python.');
    } finally {
      setIsBacktesting(false);
    }
  };

  const runValidation = async () => {
    if (isValidating) return;
    setIsValidating(true);
    setActiveTab('backtest');
    try {
      const res = await axios.post(`${BACKEND_URL}/api/strategy/validate`, {
        symbol,
        asset_type: assetType,
        interval: backtestInterval,
        period: backtestPeriod,
        strategy_code: strategyCode,
      });
      setValidationResult(res.data);
    } catch (err: unknown) {
      const detail =
        axios.isAxiosError(err) && typeof err.response?.data?.detail === 'string'
          ? err.response.data.detail
          : 'Validation failed.';
      console.error(err);
      setValidationResult({
        valid: false,
        errors: [detail],
        warnings: [],
      });
    } finally {
      setIsValidating(false);
    }
  };

  const resolveApiKeys = useCallback(async () => {
    if (Object.keys(settingsApiKeys).length > 0) {
      return settingsApiKeys;
    }
    const res = await axios.get(`${BACKEND_URL}/api/settings`);
    const apiKeys = res.data.api_keys || {};
    setSettingsApiKeys(apiKeys);
    return apiKeys as Record<string, string>;
  }, [settingsApiKeys]);

  const updateBrokerEnvironment = useCallback(
    async (nextEnv: string) => {
      if (selectedBrokerId !== 'binance' && selectedBrokerId !== 'bitget') {
        return;
      }
      setIsEnvironmentUpdating(true);
      try {
        const apiKeys = await resolveApiKeys();
        const updatedKeys = { ...apiKeys };
        if (selectedBrokerId === 'binance') {
          updatedKeys.binance_testnet = nextEnv === 'testnet' ? 'true' : 'false';
          setBinanceEnvironment(nextEnv === 'testnet' ? 'testnet' : 'live');
        }
        if (selectedBrokerId === 'bitget') {
          updatedKeys.bitget_demo = nextEnv === 'demo' ? 'true' : 'false';
          setBitgetEnvironment(nextEnv === 'demo' ? 'demo' : 'live');
        }
        await axios.post(`${BACKEND_URL}/api/settings`, { api_keys: updatedKeys });
        setSettingsApiKeys(updatedKeys);
        await fetchBrokers();
        await fetchBrokerAccount();
      } catch (err) {
        console.error('Failed to update broker environment:', err);
      } finally {
        setIsEnvironmentUpdating(false);
      }
    },
    [fetchBrokerAccount, fetchBrokers, resolveApiKeys, selectedBrokerId]
  );

  const summarizeStrategy = async () => {
    if (!strategyCode.trim() || isSummarizingStrategy) return;
    setIsSummarizingStrategy(true);
    try {
      const res = await axios.post(`${BACKEND_URL}/api/ai/summary/strategy`, {
        strategy_code: strategyCode,
        symbol,
      });
      setStrategySummary(res.data.summary || '');
    } catch (err) {
      console.error(err);
      setStrategySummary('Failed to generate AI summary. Ensure your API key is valid.');
    } finally {
      setIsSummarizingStrategy(false);
    }
  };

  const summarizeBacktest = async () => {
    if (!backtestResults || isSummarizingBacktest) return;
    setIsSummarizingBacktest(true);
    try {
      const res = await axios.post(`${BACKEND_URL}/api/ai/summary/backtest`, {
        backtest_results: backtestResults,
        symbol,
      });
      setBacktestSummary(res.data.summary || '');
    } catch (err) {
      console.error(err);
      setBacktestSummary('Failed to generate AI summary. Ensure your API key is valid.');
    } finally {
      setIsSummarizingBacktest(false);
    }
  };

  const saveCurrentStrategy = async () => {
    if (!strategyCode.trim() || isSavingStrategy) return;
    setIsSavingStrategy(true);
    try {
      const payload = {
        strategy_id: savedStrategyId || undefined,
        name: strategyName.trim() || `Strategy ${new Date().toLocaleString()}`,
        code: strategyCode,
        symbol,
        asset_type: assetType,
        tags: normalizeTags(strategyTagsInput.split(',')),
        builder_graph: builderGraph,
        validation_summary: validationResult || {},
        optimization_summary: optimizationResults?.best || {},
      };
      const res = await axios.post(`${BACKEND_URL}/api/strategies`, payload);
      setSavedStrategyId(res.data.strategy_id);
      setIsSaveModalOpen(false);
      await fetchSavedStrategies();
    } catch (err) {
      console.error(err);
      alert('Failed to save strategy.');
    } finally {
      setIsSavingStrategy(false);
    }
  };

  const updateStrategyTags = async (strategy: StrategyWorkspace, tags: string[]) => {
    const normalizedTags = normalizeTags(tags);
    try {
      await axios.post(`${BACKEND_URL}/api/strategies`, {
        strategy_id: strategy.id,
        name: strategy.name,
        code: strategy.code,
        symbol: strategy.symbol || '',
        asset_type: strategy.asset_type || assetType,
        tags: normalizedTags,
        builder_graph: strategy.builder_graph || { nodes: [], edges: [] },
        validation_summary: strategy.validation_summary || {},
        optimization_summary: strategy.optimization_summary || {},
        is_baseline: strategy.is_baseline || false,
      });
      if (savedStrategyId === strategy.id) {
        setStrategyTagsInput(normalizedTags.join(', '));
      }
      await fetchSavedStrategies();
    } catch (err) {
      console.error(err);
      alert('Failed to update strategy tags.');
    }
  };

  const loadSavedStrategy = async (strategyId: number) => {
    try {
      const res = await axios.get(`${BACKEND_URL}/api/strategies/${strategyId}`);
      const strategy = res.data;
      setStrategyName(strategy.name || '');
      setStrategyTagsInput(Array.isArray(strategy.tags) ? strategy.tags.join(', ') : '');
      setSavedStrategyId(strategy.id);
      setValidationResult(strategy.validation_summary || null);
      setOptimizationResults(
        strategy.optimization_summary?.params
          ? {
              best: strategy.optimization_summary as OptimizationCandidate,
              results: [strategy.optimization_summary as OptimizationCandidate],
            }
          : null
      );
      onLoadStrategy({
        code: strategy.code,
        builderGraph: strategy.builder_graph || { nodes: [], edges: [] },
        symbol: strategy.symbol,
        assetType: strategy.asset_type,
      });
      setActiveTab('code');
    } catch (err) {
      console.error(err);
      alert('Failed to load strategy.');
    }
  };

  const duplicateSavedStrategy = async (strategyId: number) => {
    try {
      await axios.post(`${BACKEND_URL}/api/strategies/${strategyId}/duplicate`);
      await fetchSavedStrategies();
    } catch (err) {
      console.error(err);
      alert('Failed to duplicate strategy.');
    }
  };

  const markSavedStrategyBaseline = async (strategyId: number) => {
    try {
      await axios.post(`${BACKEND_URL}/api/strategies/${strategyId}/baseline`);
      await fetchSavedStrategies();
    } catch (err) {
      console.error(err);
      alert('Failed to mark strategy as baseline.');
    }
  };

  const archiveSavedStrategy = async (strategyId: number) => {
    try {
      await axios.delete(`${BACKEND_URL}/api/strategies/${strategyId}`);
      if (savedStrategyId === strategyId) {
        setSavedStrategyId(null);
        setStrategyName('');
      }
      await fetchSavedStrategies();
    } catch (err) {
      console.error(err);
      alert('Failed to archive strategy.');
    }
  };

  const restoreSavedStrategy = async (strategyId: number) => {
    try {
      await axios.post(`${BACKEND_URL}/api/strategies/${strategyId}/restore`);
      await fetchSavedStrategies();
    } catch (err) {
      console.error(err);
      alert('Failed to restore strategy.');
    }
  };

  const toggleStrategySelection = (strategyId: number) => {
    setSelectedStrategyIds((current) =>
      current.includes(strategyId)
        ? current.filter((id) => id !== strategyId)
        : [...current, strategyId]
    );
  };

  const clearStrategySelection = () => {
    setSelectedStrategyIds([]);
  };

  const runBulkStrategyAction = async (action: 'archive' | 'restore' | 'delete') => {
    if (selectedStrategyIds.length === 0) {
      return;
    }

    try {
      await axios.post(`${BACKEND_URL}/api/strategies/bulk/${action}`, {
        strategy_ids: selectedStrategyIds,
      });

      if (action !== 'restore' && selectedStrategyIds.includes(savedStrategyId || -1)) {
        setSavedStrategyId(null);
        setStrategyName('');
      }

      clearStrategySelection();
      await fetchSavedStrategies();
    } catch (err) {
      console.error(err);
      alert(`Failed to ${action} selected strategies.`);
    }
  };

  const runOptimization = async () => {
    if (isOptimizing) return;
    setIsOptimizing(true);
    setActiveTab('optimize');
    try {
      const parseRangeList = (value: string) =>
        value
          .split(',')
          .map((item) => Number(item.trim()))
          .filter((item) => Number.isFinite(item) && item > 0);

      const customRanges =
        optimizerType === 'sma_cross'
          ? {
              sma_fast: parseRangeList(optimizerRanges.sma_fast),
              sma_slow: parseRangeList(optimizerRanges.sma_slow),
            }
          : optimizerType === 'macd_rsi'
            ? {
                rsi_period: parseRangeList(optimizerRanges.rsi_period),
                rsi_buy: parseRangeList(optimizerRanges.rsi_buy),
                rsi_sell: parseRangeList(optimizerRanges.rsi_sell),
                stop_loss_pct: parseRangeList(optimizerRanges.stop_loss_pct),
                take_profit_pct: parseRangeList(optimizerRanges.take_profit_pct),
                cooldown_bars: parseRangeList(optimizerRanges.cooldown_bars),
                position_size_pct: parseRangeList(optimizerRanges.position_size_pct),
              }
            : {
                ema_fast: parseRangeList(optimizerRanges.ema_fast),
                ema_slow: parseRangeList(optimizerRanges.ema_slow),
                rsi_period: parseRangeList(optimizerRanges.rsi_period),
                rsi_buy: parseRangeList(optimizerRanges.rsi_buy),
                rsi_sell: parseRangeList(optimizerRanges.rsi_sell),
                stop_loss_pct: parseRangeList(optimizerRanges.stop_loss_pct),
                take_profit_pct: parseRangeList(optimizerRanges.take_profit_pct),
                cooldown_bars: parseRangeList(optimizerRanges.cooldown_bars),
                position_size_pct: parseRangeList(optimizerRanges.position_size_pct),
              };

      if (optimizerType === 'sma_cross') {
        customRanges.stop_loss_pct = parseRangeList(optimizerRanges.stop_loss_pct);
        customRanges.take_profit_pct = parseRangeList(optimizerRanges.take_profit_pct);
        customRanges.cooldown_bars = parseRangeList(optimizerRanges.cooldown_bars);
        customRanges.position_size_pct = parseRangeList(optimizerRanges.position_size_pct);
      }

      const res = await axios.post(`${BACKEND_URL}/api/strategy/optimize`, {
        symbol,
        asset_type: assetType,
        interval: backtestInterval,
        period: backtestPeriod,
        strategy_type: optimizerType,
        initial_balance: initialBalance,
        fee_pct: feePct,
        slippage_pct: slippagePct,
        custom_ranges: customRanges,
      });
      setOptimizationResults(res.data);
      setOptimizationHistory((current) => [
        {
          id: Date.now(),
          label: `${optimizerType} | ${backtestInterval} | ${backtestPeriod}`,
          timestamp: new Date().toLocaleTimeString(),
          scenario: res.data.scenario,
          best: res.data.best,
          results: res.data.results,
        },
        ...current,
      ].slice(0, 6));
      if (res.data?.best?.code) {
        setStrategyCode(res.data.best.code);
      }
    } catch (err) {
      console.error(err);
      alert('Optimization failed. Check backend data availability.');
    } finally {
      setIsOptimizing(false);
    }
  };

  const applyOptimizedCode = (code: string) => {
    setStrategyCode(code);
    setActiveTab('code');
  };

  const toggleLiveTrading = async () => {
    const newStatus = !isLiveTrading;
    try {
      if (newStatus && executionMode === 'live') {
        const preflight = await axios.post<TradingPreflightResponse>(`${BACKEND_URL}/api/trading/preflight`, {
          symbol,
          asset_type: assetType,
          broker_id: selectedBrokerId,
          execution_mode: executionMode,
        });
        const accountWarnings = preflight.data.account?.warnings || [];
        const validationWarnings = preflight.data.validation?.warnings || [];
        const allWarnings = [...accountWarnings, ...validationWarnings];
        const warningText = allWarnings.length ? `\nWarnings: ${allWarnings.join(', ')}` : '';
        const qtyText =
          preflight.data.validation?.normalized_qty && preflight.data.validation?.original_qty
            ? `\nOrder Preview: ${preflight.data.validation.original_qty} requested -> ${preflight.data.validation.normalized_qty} exchange qty`
            : '';
        const priceText = preflight.data.market_price
          ? `\nReference Price: ${preflight.data.market_price.toFixed(4)}`
          : '';
        const notionalText = preflight.data.validation?.estimated_notional
          ? `\nEstimated Notional: ${preflight.data.validation.estimated_notional.toFixed(4)}`
          : '';
        const confirmed = window.confirm(
          `You are about to start LIVE trading via ${preflight.data.broker.display_name} for ${symbol}.${priceText}${qtyText}${notionalText}${warningText}\n\nContinue?`
        );
        if (!confirmed) {
          return;
        }
      }

      await axios.post(`${BACKEND_URL}/api/trading/toggle`, {
        is_active: newStatus,
        symbol,
        asset_type: assetType,
        interval: backtestInterval,
        broker_id: selectedBrokerId,
        execution_mode: executionMode,
        strategy_code: strategyCode,
      });
      setIsLiveTrading(newStatus);
      await fetchTradeHistory(newStatus && executionMode === 'live');
      if (newStatus) setActiveTab('logs');
    } catch {
      alert('Failed to toggle live trading. Check backend.');
    }
  };

  const testBrokerOrder = async () => {
    if (isTestingOrder) return;
    setIsTestingOrder(true);
    try {
      const res = await axios.post<TradingTestOrderResponse>(`${BACKEND_URL}/api/trading/test-order`, {
        symbol,
        asset_type: assetType,
        broker_id: selectedBrokerId,
        execution_mode: executionMode,
        side: 'BUY',
        qty: 1.0,
      });
      const warnings = res.data.validation?.warnings?.length
        ? `\nWarnings: ${res.data.validation.warnings.join(', ')}`
        : '';
      const priceText = res.data.market_price ? `\nReference Price: ${res.data.market_price.toFixed(4)}` : '';
      const qtyText =
        res.data.validation?.normalized_qty && res.data.validation?.original_qty
          ? `\nOrder Preview: ${res.data.validation.original_qty} requested -> ${res.data.validation.normalized_qty} exchange qty`
          : '';
      const environmentText = res.data.environment ? `\nEnvironment: ${res.data.environment}` : '';
      await fetchTradeHistory(true);
      window.alert(`${res.data.message}${environmentText}${priceText}${qtyText}${warnings}`);
    } catch (err: unknown) {
      const detail =
        axios.isAxiosError(err) && typeof err.response?.data?.detail === 'string'
          ? err.response.data.detail
          : 'Broker test order failed.';
      window.alert(detail);
    } finally {
      setIsTestingOrder(false);
    }
  };

  const applyScenarioPreset = (preset: 'conservative' | 'balanced' | 'aggressive') => {
    if (preset === 'conservative') {
      setBacktestInterval('4h');
      setBacktestPeriod('1y');
      setInitialBalance(5000);
      setFeePct(0.2);
      setSlippagePct(0.1);
      return;
    }

    if (preset === 'aggressive') {
      setBacktestInterval('15m');
      setBacktestPeriod('3mo');
      setInitialBalance(25000);
      setFeePct(0.05);
      setSlippagePct(0.03);
      return;
    }

    setBacktestInterval('1h');
    setBacktestPeriod('6mo');
    setInitialBalance(10000);
    setFeePct(0.1);
    setSlippagePct(0.05);
  };

  const cancelTradeOrder = async (tradeId: number) => {
    if (isCancellingTradeId !== null) return;
    setIsCancellingTradeId(tradeId);
    try {
      const res = await axios.post(`${BACKEND_URL}/api/trading/cancel-order`, { trade_id: tradeId });
      await fetchTradeHistory(true);
      await fetchOpenOrders();
      await fetchBrokerPositions();
      await fetchBrokerPortfolioSnapshot();
      window.alert(res.data.message || 'Order cancellation sent.');
    } catch (err: unknown) {
      const detail =
        axios.isAxiosError(err) && typeof err.response?.data?.detail === 'string'
          ? err.response.data.detail
          : 'Failed to cancel broker order.';
      window.alert(detail);
    } finally {
      setIsCancellingTradeId(null);
    }
  };

  const visibleTradeHistory = tradeHistory.filter((trade) => {
    if (tradeHistoryFilter === 'filled') {
      return trade.order_status === 'filled';
    }
    if (tradeHistoryFilter === 'tests') {
      return Boolean(trade.is_test);
    }
    if (tradeHistoryFilter === 'issues') {
      return trade.order_status === 'rejected' || trade.order_status === 'expired';
    }
    if (tradeHistoryFilter === 'open') {
      return !trade.is_test && !['filled', 'canceled', 'cancelled', 'rejected', 'expired', 'tested'].includes(trade.order_status || '');
    }
    return true;
  });

  const getTradeProgress = (trade: TradeRecord) => {
    const metadata = trade.metadata || {};
    const executedQty = typeof metadata.executed_qty === 'number' ? metadata.executed_qty : 0;
    const originalQty =
      typeof metadata.orig_qty === 'number'
        ? metadata.orig_qty
        : typeof trade.qty === 'number'
          ? trade.qty
          : 0;
    const fillProgressPct =
      typeof metadata.fill_progress_pct === 'number'
        ? metadata.fill_progress_pct
        : originalQty > 0
          ? (executedQty / originalQty) * 100
          : 0;

    return {
      executedQty,
      originalQty,
      fillProgressPct,
    };
  };

  const getTradeReason = (trade: TradeRecord) => {
    const metadata = trade.metadata || {};
    if (typeof metadata.status_refresh_error === 'string' && metadata.status_refresh_error) {
      return metadata.status_refresh_error;
    }
    if (typeof metadata.broker_reason === 'string' && metadata.broker_reason) {
      return metadata.broker_reason;
    }
    if (typeof metadata.rejectReason === 'string' && metadata.rejectReason) {
      return metadata.rejectReason;
    }
    return '';
  };

  const brokerPortfolioSummary = {
    positionCount: brokerPortfolioSnapshot.positions.length,
    openOrderCount: brokerPortfolioSnapshot.openOrders.length,
    unrealizedPl: brokerPortfolioSnapshot.positions.reduce((sum, position) => sum + (position.unrealized_pl || 0), 0),
    marketValue: brokerPortfolioSnapshot.positions.reduce((sum, position) => sum + (position.market_value || 0), 0),
    cashLikeBalance: brokerAccountSummary?.balances.reduce((sum, balance) => {
      const asset = balance.asset.toLowerCase();
      if (asset.includes('usd') || asset.includes('usdt') || asset.includes('buying power') || asset.includes('cash')) {
        return sum + balance.free;
      }
      return sum;
    }, 0) || 0,
  };

  const executionSummaryRows = Array.from(
    new Set([
      ...tradeHistory.map((trade) => trade.symbol || ''),
      ...brokerOpenOrders.map((order) => order.symbol || ''),
      ...brokerPositions.map((position) => position.symbol || ''),
    ].filter(Boolean))
  ).map((itemSymbol) => {
    const symbolTrades = tradeHistory.filter((trade) => trade.symbol === itemSymbol && !trade.is_test);
    const symbolOpenOrders = brokerOpenOrders.filter((order) => order.symbol === itemSymbol);
    const symbolPosition = brokerPositions.find((position) => position.symbol === itemSymbol);

    const buyQty = symbolTrades
      .filter((trade) => trade.side === 'BUY')
      .reduce((sum, trade) => sum + (trade.qty || 0), 0);
    const sellQty = symbolTrades
      .filter((trade) => trade.side === 'SELL')
      .reduce((sum, trade) => sum + (trade.qty || 0), 0);
    const buyValue = symbolTrades
      .filter((trade) => trade.side === 'BUY')
      .reduce((sum, trade) => sum + ((trade.qty || 0) * trade.price), 0);
    const sellValue = symbolTrades
      .filter((trade) => trade.side === 'SELL')
      .reduce((sum, trade) => sum + ((trade.qty || 0) * trade.price), 0);
    const closedTradeReturns = symbolTrades.reduce<number[]>((returns, trade) => {
      if (trade.side !== 'SELL') {
        return returns;
      }
      const qty = trade.qty || 0;
      const sellValueForTrade = qty * trade.price;
      const estimatedCostBasis = avgEntryForBuys(symbolTrades) * qty;
      if (estimatedCostBasis > 0) {
        returns.push(((sellValueForTrade - estimatedCostBasis) / estimatedCostBasis) * 100);
      }
      return returns;
    }, []);

    const realizedPl = sellValue - buyValue;
    const netQty = buyQty - sellQty;
    const avgEntry = buyQty > 0 ? buyValue / buyQty : 0;
    const winRate =
      closedTradeReturns.length > 0
        ? (closedTradeReturns.filter((value) => value > 0).length / closedTradeReturns.length) * 100
        : 0;
    const avgClosedReturn =
      closedTradeReturns.length > 0
        ? closedTradeReturns.reduce((sum, value) => sum + value, 0) / closedTradeReturns.length
        : 0;

    return {
      symbol: itemSymbol,
      tradeCount: symbolTrades.length,
      openOrders: symbolOpenOrders.length,
      netQty,
      avgEntry,
      realizedPl,
      winRate,
      avgClosedReturn,
      unrealizedPl: symbolPosition?.unrealized_pl || 0,
      marketValue: symbolPosition?.market_value || 0,
      status:
        symbolOpenOrders.length > 0
          ? 'active'
          : symbolPosition
            ? 'held'
            : symbolTrades.length > 0
              ? 'closed'
              : 'idle',
    };
  });

  const executionAnalytics = {
    winningSymbols: executionSummaryRows.filter((row) => row.realizedPl > 0).length,
    losingSymbols: executionSummaryRows.filter((row) => row.realizedPl < 0).length,
    closedSymbols: executionSummaryRows.filter((row) => row.status === 'closed').length,
    testOrderCount: tradeHistory.filter((trade) => trade.is_test).length,
    avgHoldHours:
      (() => {
        const holdDurations = executionSummaryRows.flatMap((row) => {
          const symbolTrades = tradeHistory
            .filter((trade) => trade.symbol === row.symbol && !trade.is_test)
            .slice()
            .sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp));
          let openTimestamp: number | null = null;
          const durations: number[] = [];
          for (const trade of symbolTrades) {
            const tradeTimestamp = Date.parse(trade.timestamp);
            if (Number.isNaN(tradeTimestamp)) {
              continue;
            }
            if (trade.side === 'BUY' && openTimestamp === null) {
              openTimestamp = tradeTimestamp;
            } else if (trade.side === 'SELL' && openTimestamp !== null) {
              durations.push((tradeTimestamp - openTimestamp) / (1000 * 60 * 60));
              openTimestamp = null;
            }
          }
          return durations;
        });
        if (holdDurations.length === 0) {
          return 0;
        }
        return holdDurations.reduce((sum, value) => sum + value, 0) / holdDurations.length;
      })(),
  };

  function avgEntryForBuys(symbolTrades: TradeRecord[]) {
    const buyQty = symbolTrades
      .filter((trade) => trade.side === 'BUY')
      .reduce((sum, trade) => sum + (trade.qty || 0), 0);
    const buyValue = symbolTrades
      .filter((trade) => trade.side === 'BUY')
      .reduce((sum, trade) => sum + ((trade.qty || 0) * trade.price), 0);
    return buyQty > 0 ? buyValue / buyQty : 0;
  }

  const TABS = [
    { id: 'code', label: 'Strategy Code' },
    { id: 'backtest', label: 'Backtest Results' },
    { id: 'optimize', label: 'Optimize' },
    { id: 'positions', label: 'Open Positions' },
    { id: 'logs', label: 'Terminal Logs' },
  ];

  const formatPercent = (val: number | undefined | null) => {
    if (val === undefined || val === null) return '0.00%';
    return `${val > 0 ? '+' : ''}${val.toFixed(2)}%`;
  };

  const getNormalizedBarWidth = (value: number, values: number[]) => {
    const max = Math.max(...values.map((item) => Math.abs(item)), 1);
    return `${Math.max((Math.abs(value) / max) * 100, 8)}%`;
  };

  const activeStrategies = savedStrategies.filter((strategy) => !strategy.is_archived);
  const availableTags = Array.from(new Set(savedStrategies.flatMap((strategy) => strategy.tags || []))).sort((left, right) => left.localeCompare(right));
  const tagCounts = savedStrategies.reduce<Record<string, number>>((counts, strategy) => {
    (strategy.tags || []).forEach((tag) => {
      counts[tag] = (counts[tag] || 0) + 1;
    });
    return counts;
  }, {});
  const parsedStrategyTags = normalizeTags(strategyTagsInput.split(','));
  const visibleStrategies = savedStrategies
    .filter((strategy) => {
      const query = strategySearch.trim().toLowerCase();
      const matchesQuery =
        !query ||
        strategy.name?.toLowerCase().includes(query) ||
        strategy.symbol?.toLowerCase().includes(query);

      if (!matchesQuery) {
        return false;
      }

      if (selectedTagFilters.length > 0 && !selectedTagFilters.every((tag) => (strategy.tags || []).includes(tag))) {
        return false;
      }

      if (strategyFilter === 'baseline') {
        return Boolean(strategy.is_baseline);
      }
      if (strategyFilter === 'validated') {
        return Boolean(strategy.validation_summary?.valid);
      }
      if (strategyFilter === 'issues') {
        return Array.isArray(strategy.validation_summary?.errors) && strategy.validation_summary.errors.length > 0;
      }
      return true;
    })
    .sort((left, right) => {
      if (strategySort === 'name') {
        return (left.name || '').localeCompare(right.name || '');
      }
      if (strategySort === 'symbol') {
        return (left.symbol || '').localeCompare(right.symbol || '');
      }
      return (right.last_modified || '').localeCompare(left.last_modified || '');
    });
  const groupedVisibleStrategies = Object.entries(
    visibleStrategies.reduce<Record<string, StrategyWorkspace[]>>((groups, strategy) => {
      const primaryTag = [...(strategy.tags || [])].sort((left, right) => left.localeCompare(right))[0] || 'untagged';
      if (!groups[primaryTag]) {
        groups[primaryTag] = [];
      }
      groups[primaryTag].push(strategy);
      return groups;
    }, {})
  ).sort(([left], [right]) => {
    if (left === 'untagged') return 1;
    if (right === 'untagged') return -1;
    return left.localeCompare(right);
  });
  const selectedVisibleStrategies = visibleStrategies.filter((strategy) => selectedStrategyIds.includes(strategy.id));
  const allVisibleSelected = visibleStrategies.length > 0 && visibleStrategies.every((strategy) => selectedStrategyIds.includes(strategy.id));
  const allSelectedArchived = selectedVisibleStrategies.length > 0 && selectedVisibleStrategies.every((strategy) => strategy.is_archived);
  const comparedLeft = activeStrategies.find((strategy) => strategy.id === compareLeftId) || null;
  const comparedRight = activeStrategies.find((strategy) => strategy.id === compareRightId) || null;

  const renderStrategyComparisonCard = (strategy: StrategyWorkspace | null, sideLabel: string) => {
    if (!strategy) {
      return (
        <div className="bg-[#16161e] border border-dashed border-[#2a2a35] rounded-lg p-4 text-gray-500">
          Select a saved strategy for the {sideLabel.toLowerCase()} side.
        </div>
      );
    }

    const validation = strategy.validation_summary || {};
    const optimization = strategy.optimization_summary || {};

    return (
      <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-widest text-gray-500">{sideLabel}</div>
            <div className="text-white font-bold mt-1">{strategy.name}</div>
          </div>
          <button
            onClick={() => loadSavedStrategy(strategy.id)}
            className="px-2.5 py-1 text-[10px] rounded bg-[#a55eea] text-white hover:bg-[#b87ef7] transition-colors"
          >
            Load
          </button>
        </div>

        <div className="grid grid-cols-2 gap-3 text-[10px]">
          <div>
            <div className="text-gray-500 uppercase tracking-widest">Market</div>
            <div className="text-gray-200 mt-1">{strategy.symbol || 'No symbol'} | {strategy.asset_type || 'unknown'}</div>
          </div>
          <div>
            <div className="text-gray-500 uppercase tracking-widest">Updated</div>
            <div className="text-gray-200 mt-1">{strategy.last_modified}</div>
          </div>
          <div>
            <div className="text-gray-500 uppercase tracking-widest">Validation</div>
            <div className={`mt-1 font-bold ${validation.valid ? 'text-emerald-400' : 'text-amber-300'}`}>
              {validation.valid ? 'Passed' : validation.errors?.length ? 'Issues found' : 'Not run'}
            </div>
          </div>
          <div>
            <div className="text-gray-500 uppercase tracking-widest">Graph</div>
            <div className="text-gray-200 mt-1">
              {(strategy.builder_graph?.nodes?.length || 0)} nodes | {(strategy.builder_graph?.edges?.length || 0)} edges
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 text-[10px]">
          <div className="bg-[#111118] border border-[#2a2a35] rounded p-3">
            <div className="text-gray-500 uppercase tracking-widest">Opt Return</div>
            <div className={`mt-1 font-bold ${(optimization.metrics?.total_return_pct ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {optimization.metrics ? formatPercent(optimization.metrics.total_return_pct ?? 0) : 'N/A'}
            </div>
          </div>
          <div className="bg-[#111118] border border-[#2a2a35] rounded p-3">
            <div className="text-gray-500 uppercase tracking-widest">Opt Drawdown</div>
            <div className="mt-1 font-bold text-red-400">
              {optimization.metrics ? formatPercent(optimization.metrics.max_drawdown_pct) : 'N/A'}
            </div>
          </div>
        </div>

        <div>
          <div className="text-gray-500 uppercase tracking-widest text-[10px]">Code Preview</div>
          <pre className="mt-2 text-[10px] text-gray-300 whitespace-pre-wrap max-h-48 overflow-y-auto bg-[#111118] border border-[#2a2a35] rounded p-3">
            {strategy.code}
          </pre>
        </div>
      </div>
    );
  };

  const renderRangeInput = (label: string, key: string) => (
    <label className="text-[10px] text-gray-400 uppercase tracking-wider">
      {label}
      <input
        value={optimizerRanges[key]}
        onChange={(e) => setOptimizerRanges((current) => ({ ...current, [key]: e.target.value }))}
        placeholder="comma,separated,values"
        className="mt-1 w-full bg-[#1c1c24] border border-[#2a2a35] rounded px-2 py-2 text-xs text-white"
      />
    </label>
  );

  const toggleTagPreset = (tag: string) => {
    const nextTags = parsedStrategyTags.includes(tag)
      ? parsedStrategyTags.filter((existingTag) => existingTag !== tag)
      : [...parsedStrategyTags, tag];
    setStrategyTagsInput(nextTags.join(', '));
  };

  const toggleTagFilter = (tag: string) => {
    setSelectedTagFilters((current) =>
      current.includes(tag)
        ? current.filter((existingTag) => existingTag !== tag)
        : [...current, tag]
    );
  };

  const renameTagEverywhere = async (fromTag: string, toTag: string) => {
    const normalizedTag = toTag.trim();
    if (!normalizedTag || normalizedTag === fromTag) {
      return;
    }

    try {
      await Promise.all(
        savedStrategies
          .filter((strategy) => (strategy.tags || []).includes(fromTag))
          .map((strategy) =>
            axios.post(`${BACKEND_URL}/api/strategies`, {
              strategy_id: strategy.id,
              name: strategy.name,
              code: strategy.code,
              symbol: strategy.symbol || '',
              asset_type: strategy.asset_type || assetType,
              tags: Array.from(new Set((strategy.tags || []).map((tag) => (tag === fromTag ? normalizedTag : tag)))),
              builder_graph: strategy.builder_graph || { nodes: [], edges: [] },
              validation_summary: strategy.validation_summary || {},
              optimization_summary: strategy.optimization_summary || {},
              is_baseline: strategy.is_baseline || false,
            })
          )
      );

      setSelectedTagFilters((current) => current.map((tag) => (tag === fromTag ? normalizedTag : tag)));
      if (parsedStrategyTags.includes(fromTag)) {
        setStrategyTagsInput(
          Array.from(new Set(parsedStrategyTags.map((tag) => (tag === fromTag ? normalizedTag : tag)))).join(', ')
        );
      }
      await fetchSavedStrategies();
    } catch (err) {
      console.error(err);
      alert('Failed to rename tag across strategies.');
    }
  };

  const renderStrategyCard = (strategy: StrategyWorkspace) => (
    <div
      key={strategy.id}
      className={`text-left bg-[#16161e] border rounded-lg p-3 transition-colors ${
        selectedStrategyIds.includes(strategy.id)
          ? 'border-[#a55eea]'
          : strategy.is_baseline
            ? 'border-amber-500/50'
            : 'border-[#2a2a35] hover:border-[#a55eea]'
      }`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={selectedStrategyIds.includes(strategy.id)}
            onChange={() => toggleStrategySelection(strategy.id)}
            className="accent-[#a55eea]"
          />
          <div className="text-sm font-bold text-white">{strategy.name}</div>
          {strategy.is_baseline && (
            <span className="px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-300 text-[10px] font-bold uppercase tracking-widest">
              Baseline
            </span>
          )}
          {strategy.is_archived && (
            <span className="px-2 py-0.5 rounded-full bg-red-500/15 text-red-300 text-[10px] font-bold uppercase tracking-widest">
              Archived
            </span>
          )}
        </div>
        <div className="text-[10px] text-gray-500">{strategy.last_modified}</div>
      </div>
      <div className="text-[10px] text-gray-400 mt-2">{strategy.symbol || 'No symbol'} | {strategy.asset_type || 'unknown'}</div>
      {(strategy.tags?.length ?? 0) > 0 && (
        <div className="flex flex-wrap gap-1 mt-2">
          {strategy.tags?.map((tag) => (
            <button
              key={`${strategy.id}-${tag}`}
              onClick={() => updateStrategyTags(strategy, (strategy.tags || []).filter((existingTag) => existingTag !== tag))}
              className="px-2 py-0.5 rounded-full bg-[#1f2430] text-[10px] text-sky-300 border border-sky-500/20 hover:border-red-400/40 hover:text-red-300 transition-colors"
              title="Remove tag"
            >
              {tag}
            </button>
          ))}
        </div>
      )}
      <div className="flex flex-wrap gap-2 mt-3">
        <button
          onClick={() => loadSavedStrategy(strategy.id)}
          className="px-2.5 py-1 rounded bg-[#a55eea] text-white text-[10px] hover:bg-[#b87ef7] transition-colors"
        >
          Load
        </button>
        <button
          onClick={() => duplicateSavedStrategy(strategy.id)}
          className="px-2.5 py-1 rounded bg-[#1f6feb] text-white text-[10px] hover:bg-[#388bfd] transition-colors"
        >
          Duplicate
        </button>
        {!strategy.is_archived ? (
          <>
            <button
              onClick={() => {
                const nextTag = window.prompt('Add tag to strategy:', '');
                if (!nextTag) return;
                const normalizedTag = nextTag.trim();
                const finalTag = normalizeTags([normalizedTag])[0];
                if (!finalTag || (strategy.tags || []).includes(finalTag)) return;
                void updateStrategyTags(strategy, [...(strategy.tags || []), finalTag]);
              }}
              className="px-2.5 py-1 rounded bg-sky-700 text-white text-[10px] hover:bg-sky-600 transition-colors"
            >
              Add Tag
            </button>
            <button
              onClick={() => markSavedStrategyBaseline(strategy.id)}
              className="px-2.5 py-1 rounded bg-amber-600 text-white text-[10px] hover:bg-amber-500 transition-colors"
            >
              Set Baseline
            </button>
            <button
              onClick={() => archiveSavedStrategy(strategy.id)}
              className="px-2.5 py-1 rounded bg-red-700 text-white text-[10px] hover:bg-red-600 transition-colors"
            >
              Archive
            </button>
          </>
        ) : (
          <button
            onClick={() => restoreSavedStrategy(strategy.id)}
            className="px-2.5 py-1 rounded bg-emerald-700 text-white text-[10px] hover:bg-emerald-600 transition-colors"
          >
            Restore
          </button>
        )}
      </div>
    </div>
  );

  const showEnvironmentSelector = selectedBrokerId === 'binance' || selectedBrokerId === 'bitget';
  const currentEnvironment =
    selectedBrokerId === 'binance'
      ? binanceEnvironment
      : selectedBrokerId === 'bitget'
        ? bitgetEnvironment
        : 'live';
  const environmentOptions =
    selectedBrokerId === 'binance'
      ? [
          { value: 'live', label: 'Live' },
          { value: 'testnet', label: 'Testnet' },
        ]
      : selectedBrokerId === 'bitget'
        ? [
            { value: 'live', label: 'Live' },
            { value: 'demo', label: 'Demo' },
          ]
        : [{ value: 'live', label: 'Live' }];
  const brokerConfigGridClass = showEnvironmentSelector ? 'grid-cols-1 md:grid-cols-3' : 'grid-cols-1 md:grid-cols-2';

  return (
    <div className="w-full h-full flex flex-col bg-[#0f0f13]">
      {isSaveModalOpen && (
        <div className="absolute inset-0 z-30 bg-[#0a0a0c]/90 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#1c1c26] border border-[#a55eea]/30 rounded-2xl w-full max-w-xl p-5 shadow-2xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-bold text-white">Save Strategy Workspace</h3>
              <button onClick={() => setIsSaveModalOpen(false)} className="text-gray-500 hover:text-white transition-colors">Close</button>
            </div>
            <label className="block text-xs text-gray-400 mb-2">
              Strategy Name
              <input
                value={strategyName}
                onChange={(e) => setStrategyName(e.target.value)}
                placeholder="Momentum Risk Model"
                className="mt-1 w-full bg-[#0a0a0c] border border-[#2a2a35] rounded-lg py-2 px-3 text-white"
              />
            </label>
            <label className="block text-xs text-gray-400 mb-4">
              Tags
              <input
                value={strategyTagsInput}
                onChange={(e) => setStrategyTagsInput(e.target.value)}
                placeholder="crypto, swing, mean-reversion"
                className="mt-1 w-full bg-[#0a0a0c] border border-[#2a2a35] rounded-lg py-2 px-3 text-white"
              />
            </label>
            <div className="flex flex-wrap gap-2 mb-4">
              {tagPresets.map((tag) => (
                <button
                  key={tag}
                  onClick={() => toggleTagPreset(tag)}
                  className={`px-2 py-1 rounded-full text-[10px] border transition-colors ${
                    parsedStrategyTags.includes(tag)
                      ? 'bg-sky-500/15 border-sky-500 text-sky-300'
                      : 'bg-[#111118] border-[#2a2a35] text-gray-400 hover:border-sky-500/40'
                  }`}
                >
                  {tag}
                </button>
              ))}
            </div>
            <div className="text-[11px] text-gray-500 mb-4">
              This saves strategy code, tags, builder graph, current validation summary, and latest optimization best result.
            </div>
            <button onClick={saveCurrentStrategy} className="w-full bg-[#a55eea] hover:bg-[#b87ef7] text-white font-bold py-2.5 rounded-lg transition-all" disabled={isSavingStrategy}>
              {isSavingStrategy ? 'Saving...' : 'Save Workspace'}
            </button>
          </div>
        </div>
      )}

      <div className="flex items-center gap-2 pb-2 border-b border-[#2a2a35] flex-shrink-0">
        <input
          type="text"
          value={strategyPrompt}
          onChange={(e) => setStrategyPrompt(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && generateStrategy()}
          placeholder={isGenerating ? 'Generating...' : 'Describe your strategy (e.g. MACD + RSI oversold, Bollinger breakout)'}
          className="flex-1 bg-[#1c1c24] text-xs text-white rounded-lg border border-[#2a2a35] focus:border-[#a55eea] focus:ring-1 focus:ring-[#a55eea] outline-none py-2 px-3 transition-all disabled:opacity-50"
          disabled={isGenerating}
        />
        <div className="flex gap-2">
          <button
            onClick={generateStrategy}
            disabled={isGenerating || !strategyPrompt.trim()}
            className="px-4 py-2 text-xs font-semibold rounded-lg bg-[#a55eea] text-white hover:bg-[#b87ef7] transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5"
          >
            {isGenerating ? (
              <><span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin inline-block"></span> Generating</>
            ) : (
              <>Generate</>
            )}
          </button>

          <button
            onClick={() => setIsSaveModalOpen(true)}
            className="px-4 py-2 text-xs font-semibold rounded-lg bg-[#6c5ce7] text-white hover:bg-[#7b6bf0] transition-colors flex items-center gap-1.5"
          >
            Save
          </button>

          <button
            onClick={runValidation}
            disabled={isValidating || !strategyCode}
            className="px-4 py-2 text-xs font-semibold rounded-lg bg-slate-700 text-white hover:bg-slate-600 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5"
          >
            {isValidating ? (
              <><span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin inline-block"></span> Validating</>
            ) : (
              <>Validate</>
            )}
          </button>

          <button
            onClick={runOptimization}
            disabled={isOptimizing}
            className="px-4 py-2 text-xs font-semibold rounded-lg bg-amber-600 text-white hover:bg-amber-500 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5"
          >
            {isOptimizing ? (
              <><span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin inline-block"></span> Optimizing</>
            ) : (
              <>Optimize</>
            )}
          </button>

          <button
            onClick={toggleLiveTrading}
            className={`px-4 py-2 text-xs font-semibold rounded-lg text-white transition-all flex items-center gap-1.5 ${
              isLiveTrading
                ? 'bg-red-600 hover:bg-red-500 shadow-[0_0_15px_rgba(220,38,38,0.4)]'
                : 'bg-indigo-600 hover:bg-indigo-500'
            }`}
          >
            {isLiveTrading ? 'Stop Live' : 'Start Live Paper'}
          </button>

          <button
            onClick={testBrokerOrder}
            disabled={isTestingOrder}
            className="px-4 py-2 text-xs font-semibold rounded-lg bg-cyan-700 text-white hover:bg-cyan-600 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5"
          >
            {isTestingOrder ? (
              <><span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin inline-block"></span> Testing Order</>
            ) : (
              <>Test Broker Order</>
            )}
          </button>

          <button
            onClick={runBacktest}
            disabled={isGenerating || isBacktesting || !strategyCode || strategyCode.includes('Your AI-generated strategy will appear here')}
            className="px-4 py-2 text-xs font-semibold rounded-lg bg-green-600 text-white hover:bg-green-500 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5"
          >
            {isBacktesting ? (
              <><span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin inline-block"></span> Testing</>
            ) : (
              <>Run Backtest</>
            )}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-2 py-3 border-b border-[#2a2a35]">
        <label className="text-[10px] text-gray-400 uppercase tracking-wider">
          Optimizer
          <select value={optimizerType} onChange={(e) => setOptimizerType(e.target.value)} className="mt-1 w-full bg-[#1c1c24] border border-[#2a2a35] rounded px-2 py-2 text-xs text-white">
            <option value="ema_rsi">EMA + RSI</option>
            <option value="sma_cross">SMA Cross</option>
            <option value="macd_rsi">MACD + RSI</option>
          </select>
        </label>
        <label className="text-[10px] text-gray-400 uppercase tracking-wider">
          Interval
          <select value={backtestInterval} onChange={(e) => setBacktestInterval(e.target.value)} className="mt-1 w-full bg-[#1c1c24] border border-[#2a2a35] rounded px-2 py-2 text-xs text-white">
            <option value="15m">15m</option>
            <option value="1h">1h</option>
            <option value="4h">4h</option>
            <option value="1d">1d</option>
          </select>
        </label>
        <label className="text-[10px] text-gray-400 uppercase tracking-wider">
          Period
          <select value={backtestPeriod} onChange={(e) => setBacktestPeriod(e.target.value)} className="mt-1 w-full bg-[#1c1c24] border border-[#2a2a35] rounded px-2 py-2 text-xs text-white">
            <option value="3mo">3 months</option>
            <option value="6mo">6 months</option>
            <option value="1y">1 year</option>
            <option value="2y">2 years</option>
          </select>
        </label>
        <label className="text-[10px] text-gray-400 uppercase tracking-wider">
          Start Capital
          <input value={initialBalance} onChange={(e) => setInitialBalance(Number(e.target.value) || 0)} type="number" min="100" step="100" className="mt-1 w-full bg-[#1c1c24] border border-[#2a2a35] rounded px-2 py-2 text-xs text-white" />
        </label>
        <label className="text-[10px] text-gray-400 uppercase tracking-wider">
          Fee %
          <input value={feePct} onChange={(e) => setFeePct(Number(e.target.value) || 0)} type="number" min="0" step="0.01" className="mt-1 w-full bg-[#1c1c24] border border-[#2a2a35] rounded px-2 py-2 text-xs text-white" />
        </label>
        <label className="text-[10px] text-gray-400 uppercase tracking-wider">
          Slippage %
          <input value={slippagePct} onChange={(e) => setSlippagePct(Number(e.target.value) || 0)} type="number" min="0" step="0.01" className="mt-1 w-full bg-[#1c1c24] border border-[#2a2a35] rounded px-2 py-2 text-xs text-white" />
        </label>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-2 py-3 border-b border-[#2a2a35]">
        {optimizerType !== 'sma_cross' && renderRangeInput('RSI Periods', 'rsi_period')}
        {optimizerType !== 'sma_cross' && renderRangeInput('RSI Buy', 'rsi_buy')}
        {optimizerType !== 'sma_cross' && renderRangeInput('RSI Sell', 'rsi_sell')}
        {optimizerType === 'ema_rsi' && renderRangeInput('EMA Fast', 'ema_fast')}
        {optimizerType === 'ema_rsi' && renderRangeInput('EMA Slow', 'ema_slow')}
        {optimizerType === 'sma_cross' && renderRangeInput('SMA Fast', 'sma_fast')}
        {optimizerType === 'sma_cross' && renderRangeInput('SMA Slow', 'sma_slow')}
        {renderRangeInput('Stop Loss %', 'stop_loss_pct')}
        {renderRangeInput('Take Profit %', 'take_profit_pct')}
        {renderRangeInput('Cooldown Bars', 'cooldown_bars')}
        {renderRangeInput('Position Size %', 'position_size_pct')}
      </div>

      <div className="flex items-center gap-2 py-2 border-b border-[#2a2a35]">
        <span className="text-[10px] uppercase tracking-widest text-gray-500">Scenario Presets</span>
        <button onClick={() => applyScenarioPreset('conservative')} className="px-2.5 py-1 text-[10px] rounded border border-[#2a2a35] bg-[#1c1c24] text-gray-300 hover:border-emerald-500/40">Conservative</button>
        <button onClick={() => applyScenarioPreset('balanced')} className="px-2.5 py-1 text-[10px] rounded border border-[#2a2a35] bg-[#1c1c24] text-gray-300 hover:border-sky-500/40">Balanced</button>
        <button onClick={() => applyScenarioPreset('aggressive')} className="px-2.5 py-1 text-[10px] rounded border border-[#2a2a35] bg-[#1c1c24] text-gray-300 hover:border-red-500/40">Aggressive</button>
      </div>

      <div className={`grid ${brokerConfigGridClass} gap-2 py-3 border-b border-[#2a2a35]`}>
        <label className="text-[10px] text-gray-400 uppercase tracking-wider">
          Broker
          <select value={selectedBrokerId} onChange={(e) => setSelectedBrokerId(e.target.value)} className="mt-1 w-full bg-[#1c1c24] border border-[#2a2a35] rounded px-2 py-2 text-xs text-white">
            {availableBrokers.map((broker) => (
              <option key={broker.broker_id} value={broker.broker_id}>
                {broker.display_name}
                {broker.environment && broker.environment !== 'live' ? ` [${broker.environment}]` : ''}
                {broker.configured ? '' : ' (No Keys)'}
              </option>
            ))}
          </select>
        </label>
        <label className="text-[10px] text-gray-400 uppercase tracking-wider">
          Execution Mode
          <select value={executionMode} onChange={(e) => setExecutionMode(e.target.value as 'paper' | 'live')} className="mt-1 w-full bg-[#1c1c24] border border-[#2a2a35] rounded px-2 py-2 text-xs text-white">
            <option value="paper">Paper</option>
            <option value="live">Live</option>
          </select>
        </label>
        <label className="text-[10px] text-gray-400 uppercase tracking-wider">
          Environment
          <select
            value={currentEnvironment}
            onChange={(e) => void updateBrokerEnvironment(e.target.value)}
            disabled={!showEnvironmentSelector || isEnvironmentUpdating}
            className="mt-1 w-full bg-[#1c1c24] border border-[#2a2a35] rounded px-2 py-2 text-xs text-white disabled:opacity-60"
          >
            {environmentOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {brokerAccountSummary && (
        <div className="border-b border-[#2a2a35] py-3">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-3">
              <div className="text-[10px] uppercase tracking-widest text-gray-500">Broker Status</div>
              <div className={`text-sm font-bold mt-1 ${brokerAccountSummary.configured ? 'text-emerald-300' : 'text-amber-300'}`}>
                {brokerAccountSummary.display_name}
                {brokerAccountSummary.environment ? ` [${brokerAccountSummary.environment}]` : ''}
                {' | '}
                {brokerAccountSummary.configured ? 'Configured' : 'Missing Keys'}
              </div>
            </div>
            <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-3">
              <div className="text-[10px] uppercase tracking-widest text-gray-500">Trade Access</div>
              <div className={`text-sm font-bold mt-1 ${brokerAccountSummary.can_trade ? 'text-emerald-300' : 'text-red-300'}`}>
                {brokerAccountSummary.can_trade ? 'Enabled' : 'Blocked'}
              </div>
            </div>
            <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-3">
              <div className="text-[10px] uppercase tracking-widest text-gray-500">Balances</div>
              <div className="text-xs text-white mt-1">
                {brokerAccountSummary.balances.length > 0
                  ? brokerAccountSummary.balances.slice(0, 3).map((balance) => `${balance.asset}: ${balance.free}`).join(' | ')
                  : 'No balances available'}
              </div>
            </div>
          </div>
          {brokerAccountSummary.warnings.length > 0 && (
            <div className="mt-2 text-[10px] text-amber-300">
              {brokerAccountSummary.warnings.join(' | ')}
            </div>
          )}
        </div>
      )}

      <div className="flex items-center gap-1 border-b border-[#2a2a35] flex-shrink-0">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-3 py-1.5 text-xs font-medium border-b-2 transition-colors ${
              activeTab === tab.id
                ? 'border-[#a55eea] text-[#a55eea]'
                : 'border-transparent text-gray-400 hover:text-gray-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="flex-1 w-full overflow-y-auto font-mono text-xs mt-2 p-3 bg-[#0a0a0c] rounded border border-[#2a2a35]">
        {activeTab === 'code' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="text-[10px] uppercase tracking-widest text-gray-500">Saved Workspaces</div>
              <div className="flex items-center gap-2">
                {availableTags.length > 0 && (
                  <button
                    onClick={() => {
                      const fromTag = window.prompt(`Rename which tag?\nAvailable: ${availableTags.join(', ')}`, selectedTagFilters[0] || availableTags[0] || '');
                      if (!fromTag) return;
                      const toTag = window.prompt(`Rename "${fromTag}" to:`, fromTag);
                      if (!toTag) return;
                      void renameTagEverywhere(fromTag, toTag);
                    }}
                    className="text-[10px] text-gray-400 hover:text-white transition-colors"
                  >
                    Rename Tag
                  </button>
                )}
                <button
                  onClick={() => setStrategyViewMode(strategyViewMode === 'flat' ? 'grouped' : 'flat')}
                  className="text-[10px] text-gray-400 hover:text-white transition-colors"
                >
                  {strategyViewMode === 'flat' ? 'Grouped View' : 'Flat View'}
                </button>
                <button onClick={fetchSavedStrategies} className="text-[10px] text-[#a55eea] hover:text-white transition-colors">Refresh</button>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              <label className="text-[10px] text-gray-400 uppercase tracking-wider">
                Collection
                <select value={strategyCollection} onChange={(e) => setStrategyCollection(e.target.value as 'active' | 'archived' | 'all')} className="mt-1 w-full bg-[#111118] border border-[#2a2a35] rounded px-2 py-2 text-xs text-white">
                  <option value="active">Active only</option>
                  <option value="archived">Archived only</option>
                  <option value="all">All workspaces</option>
                </select>
              </label>
              <label className="text-[10px] text-gray-400 uppercase tracking-wider">
                Search
                <input
                  value={strategySearch}
                  onChange={(e) => setStrategySearch(e.target.value)}
                  placeholder="Search name or symbol"
                  className="mt-1 w-full bg-[#111118] border border-[#2a2a35] rounded px-2 py-2 text-xs text-white"
                />
              </label>
              <label className="text-[10px] text-gray-400 uppercase tracking-wider">
                Filter
                <select value={strategyFilter} onChange={(e) => setStrategyFilter(e.target.value as 'all' | 'baseline' | 'validated' | 'issues')} className="mt-1 w-full bg-[#111118] border border-[#2a2a35] rounded px-2 py-2 text-xs text-white">
                  <option value="all">All strategies</option>
                  <option value="baseline">Baseline only</option>
                  <option value="validated">Validation passed</option>
                  <option value="issues">Validation issues</option>
                </select>
              </label>
              <label className="text-[10px] text-gray-400 uppercase tracking-wider">
                Sort
                <select value={strategySort} onChange={(e) => setStrategySort(e.target.value as 'updated' | 'name' | 'symbol')} className="mt-1 w-full bg-[#111118] border border-[#2a2a35] rounded px-2 py-2 text-xs text-white">
                  <option value="updated">Recently updated</option>
                  <option value="name">Name</option>
                  <option value="symbol">Symbol</option>
                </select>
              </label>
              <label className="text-[10px] text-gray-400 uppercase tracking-wider">
                Tags
                <div className="mt-1 min-h-[38px] bg-[#111118] border border-[#2a2a35] rounded px-2 py-2 text-xs text-white flex flex-wrap gap-1">
                  <button
                    onClick={() => setSelectedTagFilters([])}
                    className={`px-2 py-1 rounded-full border text-[10px] transition-colors ${
                      selectedTagFilters.length === 0
                        ? 'bg-sky-500/15 border-sky-500 text-sky-300'
                        : 'bg-transparent border-[#2a2a35] text-gray-400 hover:border-sky-500/40'
                    }`}
                  >
                    All
                  </button>
                  {availableTags.map((tag) => (
                    <button
                      key={tag}
                      onClick={() => toggleTagFilter(tag)}
                      className={`px-2 py-1 rounded-full border text-[10px] transition-colors ${
                        selectedTagFilters.includes(tag)
                          ? 'bg-sky-500/15 border-sky-500 text-sky-300'
                          : 'bg-transparent border-[#2a2a35] text-gray-400 hover:border-sky-500/40'
                      }`}
                    >
                      {tag} ({tagCounts[tag] || 0})
                    </button>
                  ))}
                </div>
              </label>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-3">
                <div className="text-[10px] uppercase tracking-widest text-gray-500">Visible</div>
                <div className="text-lg font-bold text-white mt-1">{visibleStrategies.length}</div>
              </div>
              <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-3">
                <div className="text-[10px] uppercase tracking-widest text-gray-500">Archived</div>
                <div className="text-lg font-bold text-amber-300 mt-1">{savedStrategies.filter((strategy) => strategy.is_archived).length}</div>
              </div>
              <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-3">
                <div className="text-[10px] uppercase tracking-widest text-gray-500">Baselines</div>
                <div className="text-lg font-bold text-emerald-300 mt-1">{savedStrategies.filter((strategy) => strategy.is_baseline).length}</div>
              </div>
            </div>
            {availableTags.length > 0 && (
              <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-3">
                <div className="text-[10px] uppercase tracking-widest text-gray-500 mb-2">Tag Counts</div>
                <div className="flex flex-wrap gap-2">
                  {availableTags.map((tag) => (
                    <button
                      key={`count-${tag}`}
                      onClick={() => toggleTagFilter(tag)}
                      className={`px-2 py-1 rounded-full border text-[10px] transition-colors ${
                        selectedTagFilters.includes(tag)
                          ? 'bg-sky-500/15 border-sky-500 text-sky-300'
                          : 'bg-[#111118] border-[#2a2a35] text-gray-400 hover:border-sky-500/40'
                      }`}
                    >
                      {tag} ({tagCounts[tag] || 0})
                    </button>
                  ))}
                </div>
              </div>
            )}
            {visibleStrategies.length > 0 && (
              <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-4 space-y-3">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <div className="text-[10px] uppercase tracking-widest text-gray-500">Bulk Actions</div>
                    <div className="text-xs text-gray-300 mt-1">
                      {selectedStrategyIds.length} selected
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={() => setSelectedStrategyIds(allVisibleSelected ? [] : visibleStrategies.map((strategy) => strategy.id))}
                      className="px-2.5 py-1 rounded bg-[#1f2430] text-white text-[10px] hover:bg-[#2a3140] transition-colors"
                    >
                      {allVisibleSelected ? 'Clear Visible' : 'Select Visible'}
                    </button>
                    <button
                      onClick={clearStrategySelection}
                      disabled={selectedStrategyIds.length === 0}
                      className="px-2.5 py-1 rounded bg-[#2a2a35] text-white text-[10px] hover:bg-[#3a3a48] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      Clear Selected
                    </button>
                    <button
                      onClick={() => runBulkStrategyAction('archive')}
                      disabled={selectedStrategyIds.length === 0}
                      className="px-2.5 py-1 rounded bg-red-700 text-white text-[10px] hover:bg-red-600 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      Bulk Archive
                    </button>
                    <button
                      onClick={() => runBulkStrategyAction('restore')}
                      disabled={selectedStrategyIds.length === 0}
                      className="px-2.5 py-1 rounded bg-emerald-700 text-white text-[10px] hover:bg-emerald-600 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      Bulk Restore
                    </button>
                    <button
                      onClick={() => runBulkStrategyAction('delete')}
                      disabled={!allSelectedArchived}
                      className="px-2.5 py-1 rounded bg-[#7a1f1f] text-white text-[10px] hover:bg-[#922626] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      Delete Archived
                    </button>
                  </div>
                </div>
                <div className="text-[10px] text-gray-500">
                  Permanent delete is only enabled when every selected workspace is archived.
                </div>
              </div>
            )}
            {activeStrategies.length > 1 && (
              <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-4 space-y-3">
                <div className="text-[10px] uppercase tracking-widest text-gray-500">Version Comparison</div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <label className="text-[10px] text-gray-400 uppercase tracking-wider">
                    Left Strategy
                    <select value={compareLeftId ?? ''} onChange={(e) => setCompareLeftId(e.target.value ? Number(e.target.value) : null)} className="mt-1 w-full bg-[#111118] border border-[#2a2a35] rounded px-2 py-2 text-xs text-white">
                      <option value="">Select strategy</option>
                      {activeStrategies.map((strategy) => (
                        <option key={`left-${strategy.id}`} value={strategy.id}>{strategy.name}</option>
                      ))}
                    </select>
                  </label>
                  <label className="text-[10px] text-gray-400 uppercase tracking-wider">
                    Right Strategy
                    <select value={compareRightId ?? ''} onChange={(e) => setCompareRightId(e.target.value ? Number(e.target.value) : null)} className="mt-1 w-full bg-[#111118] border border-[#2a2a35] rounded px-2 py-2 text-xs text-white">
                      <option value="">Select strategy</option>
                      {activeStrategies.map((strategy) => (
                        <option key={`right-${strategy.id}`} value={strategy.id}>{strategy.name}</option>
                      ))}
                    </select>
                  </label>
                </div>
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                  {renderStrategyComparisonCard(comparedLeft, 'Left')}
                  {renderStrategyComparisonCard(comparedRight, 'Right')}
                </div>
              </div>
            )}
            {visibleStrategies.length > 0 ? (
              strategyViewMode === 'flat' ? (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                  {visibleStrategies.map((strategy) => renderStrategyCard(strategy))}
                </div>
              ) : (
                <div className="space-y-4">
                  {groupedVisibleStrategies.map(([group, strategies]) => (
                    <div key={group} className="space-y-2">
                      <div className="flex items-center justify-between px-1">
                        <div className="text-[10px] uppercase tracking-widest text-gray-500">
                          {group === 'untagged' ? 'Untagged' : group}
                        </div>
                        <div className="text-[10px] text-gray-600">{strategies.length} strategies</div>
                      </div>
                      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                        {strategies.map((strategy) => renderStrategyCard(strategy))}
                      </div>
                    </div>
                  ))}
                </div>
              )
            ) : (
              <div className="flex flex-col items-center justify-center py-8 text-gray-500 bg-[#16161e] border border-dashed border-[#2a2a35] rounded-lg">
                <p>No saved strategies match the current view.</p>
                <p className="text-[10px] mt-1">Try changing the collection, filter, or search terms.</p>
              </div>
            )}
            <pre className="text-gray-200 whitespace-pre-wrap leading-5">{strategyCode}</pre>
            <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-3 space-y-2">
              <div className="flex items-center justify-between">
                <div className="text-[10px] uppercase tracking-widest text-gray-500">AI Strategy Summary</div>
                <button
                  onClick={summarizeStrategy}
                  disabled={isSummarizingStrategy || !strategyCode.trim()}
                  className="px-2.5 py-1 text-[10px] rounded border border-[#2a2a35] bg-[#1c1c24] text-gray-300 hover:border-[#a55eea] disabled:opacity-50"
                >
                  {isSummarizingStrategy ? 'Summarizing...' : 'Generate'}
                </button>
              </div>
              <div className="text-[11px] text-gray-300 whitespace-pre-wrap">
                {strategySummary || 'Generate a concise explanation of the current strategy.'}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'backtest' && (
          <div className="text-gray-300 space-y-4">
            <div className="flex items-center justify-between">
              <div className="text-[#a55eea] font-bold text-sm">Backtest Report ({symbol} {backtestInterval})</div>
              {isBacktesting && <div className="text-xs text-yellow-500 animate-pulse font-bold">CALCULATING METRICS...</div>}
            </div>

            {backtestResults ? (
              <>
                {validationResult && (
                  <div className={`rounded-lg border p-3 ${validationResult.valid ? 'bg-emerald-500/5 border-emerald-500/30' : 'bg-red-500/5 border-red-500/30'}`}>
                    <div className={`text-xs font-bold uppercase tracking-widest ${validationResult.valid ? 'text-emerald-400' : 'text-red-400'}`}>
                      {validationResult.valid ? 'Validation passed' : 'Validation issues detected'}
                    </div>
                    {validationResult.stats && (
                      <div className="text-[10px] text-gray-400 mt-2">
                        {validationResult.stats.rows} rows | {validationResult.stats.trade_signal_count} trade signals | [{validationResult.stats.signal_values.join(', ')}]
                      </div>
                    )}
                    {(validationResult.errors?.length ?? 0) > 0 && (
                      <div className="mt-2 space-y-1">
                        {validationResult.errors?.map((message: string, index: number) => (
                          <div key={index} className="text-[10px] text-red-300">{message}</div>
                        ))}
                      </div>
                    )}
                    {(validationResult.warnings?.length ?? 0) > 0 && (
                      <div className="mt-2 space-y-1">
                        {validationResult.warnings?.map((message: string, index: number) => (
                          <div key={index} className="text-[10px] text-amber-300">{message}</div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="text-[10px] uppercase tracking-widest text-gray-500">AI Backtest Summary</div>
                    <button
                      onClick={summarizeBacktest}
                      disabled={isSummarizingBacktest || !backtestResults}
                      className="px-2.5 py-1 text-[10px] rounded border border-[#2a2a35] bg-[#1c1c24] text-gray-300 hover:border-[#a55eea] disabled:opacity-50"
                    >
                      {isSummarizingBacktest ? 'Summarizing...' : 'Generate'}
                    </button>
                  </div>
                  <div className="text-[11px] text-gray-300 whitespace-pre-wrap">
                    {backtestSummary || 'Generate a concise summary of the latest backtest.'}
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                  <div className="bg-[#1c1c26] border border-[#2a2a35] rounded-lg p-3">
                    <div className="text-gray-500 text-[10px] uppercase tracking-wider mb-1">Total Return</div>
                    <div className={`text-xl font-bold ${(backtestResults.total_return_pct ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {formatPercent(backtestResults.total_return_pct ?? 0)}
                    </div>
                  </div>
                  <div className="bg-[#1c1c26] border border-[#2a2a35] rounded-lg p-3">
                    <div className="text-gray-500 text-[10px] uppercase tracking-wider mb-1">Max Drawdown</div>
                    <div className="text-xl font-bold text-red-400">
                      {formatPercent(backtestResults.max_drawdown_pct)}
                    </div>
                  </div>
                  <div className="bg-[#1c1c26] border border-[#2a2a35] rounded-lg p-3">
                    <div className="text-gray-500 text-[10px] uppercase tracking-wider mb-1">Trade Count</div>
                    <div className="text-xl font-bold text-white">
                      {backtestResults.trade_count}
                    </div>
                  </div>
                  <div className="bg-[#1c1c26] border border-[#2a2a35] rounded-lg p-3">
                    <div className="text-gray-500 text-[10px] uppercase tracking-wider mb-1">Final Equity</div>
                    <div className="text-xl font-bold text-blue-400">
                      ${(backtestResults.final_equity || 0).toFixed(2)}
                    </div>
                  </div>
                </div>

                {backtestResults.scenario && (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div className="bg-[#12121a] border border-[#2a2a35] rounded-lg p-3">
                      <div className="text-gray-500 text-[10px] uppercase tracking-wider mb-1">Scenario</div>
                      <div className="text-white font-bold">{backtestResults.scenario.period} @ {backtestResults.scenario.interval}</div>
                    </div>
                    <div className="bg-[#12121a] border border-[#2a2a35] rounded-lg p-3">
                      <div className="text-gray-500 text-[10px] uppercase tracking-wider mb-1">Fees / Slippage</div>
                      <div className="text-white font-bold">{backtestResults.scenario.fee_pct}% / {backtestResults.scenario.slippage_pct}%</div>
                    </div>
                    <div className="bg-[#12121a] border border-[#2a2a35] rounded-lg p-3">
                      <div className={`font-bold ${(backtestResults.buy_hold_return_pct ?? 0) >= 0 ? 'text-sky-400' : 'text-red-400'}`}>
                        {formatPercent(backtestResults.buy_hold_return_pct ?? 0)}
                      </div>
                      <div className="text-gray-500 text-[10px] uppercase tracking-wider mt-1">Buy & Hold</div>
                    </div>
                    <div className="bg-[#12121a] border border-[#2a2a35] rounded-lg p-3">
                      <div className="text-white font-bold">{(backtestResults.win_rate_pct || 0).toFixed(1)}%</div>
                      <div className="text-gray-500 text-[10px] uppercase tracking-wider mt-1">Win Rate</div>
                    </div>
                  </div>
                )}
              </>
            ) : !isBacktesting && (
              <>
                {validationResult && (
                  <div className={`rounded-lg border p-3 ${validationResult.valid ? 'bg-emerald-500/5 border-emerald-500/30' : 'bg-red-500/5 border-red-500/30'}`}>
                    <div className={`text-xs font-bold uppercase tracking-widest ${validationResult.valid ? 'text-emerald-400' : 'text-red-400'}`}>
                      {validationResult.valid ? 'Validation passed' : 'Validation issues detected'}
                    </div>
                    {validationResult.stats && (
                      <div className="text-[10px] text-gray-400 mt-2">
                        {validationResult.stats.rows} rows | {validationResult.stats.trade_signal_count} trade signals | [{validationResult.stats.signal_values.join(', ')}]
                      </div>
                    )}
                    {(validationResult.errors?.length ?? 0) > 0 && validationResult.errors?.map((message: string, index: number) => (
                      <div key={index} className="text-[10px] text-red-300 mt-2">{message}</div>
                    ))}
                    {(validationResult.warnings?.length ?? 0) > 0 && validationResult.warnings?.map((message: string, index: number) => (
                      <div key={index} className="text-[10px] text-amber-300 mt-2">{message}</div>
                    ))}
                  </div>
                )}
                <div className="flex flex-col items-center justify-center py-10 text-gray-500 bg-[#16161e] border border-dashed border-[#2a2a35] rounded-lg">
                  <span className="text-lg mb-2">Scenario runner</span>
                  <p>No backtest data available.</p>
                  <p className="text-[10px]">Validate first or run a backtest to evaluate your strategy logic.</p>
                </div>
              </>
            )}

            {(backtestResults?.trade_history?.length ?? 0) > 0 && (
              <div className="mt-4">
                <div className="text-[10px] text-gray-500 uppercase tracking-widest mb-2 px-1">Recent Trades</div>
                <div className="bg-[#16161e] border border-[#2a2a35] rounded overflow-hidden">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="bg-[#2a2a35]/30 text-gray-500 text-[10px]">
                        <th className="p-2 border-b border-[#2a2a35]">Type</th>
                        <th className="p-2 border-b border-[#2a2a35]">Price</th>
                        <th className="p-2 border-b border-[#2a2a35]">Balance</th>
                        <th className="p-2 border-b border-[#2a2a35]">Time</th>
                      </tr>
                    </thead>
                    <tbody className="text-[10px]">
                      {backtestResults?.trade_history?.slice(-5).reverse().map((trade: TradeRecord, index: number) => (
                        <tr key={index} className="border-b border-[#2a2a35]/50 hover:bg-white/5 transition-colors">
                          <td className={`p-2 font-bold ${trade.type === 'BUY' ? 'text-green-400' : 'text-red-400'}`}>{trade.type}</td>
                          <td className="p-2 text-gray-300 font-bold">${trade.price.toLocaleString()}</td>
                          <td className="p-2 text-gray-400">${(trade.balance ?? 0).toFixed(2)}</td>
                          <td className="p-2 text-gray-500">{trade.timestamp}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'optimize' && (
          <div className="space-y-4 text-gray-300">
            <div className="flex items-center justify-between">
              <div className="text-[#a55eea] font-bold text-sm">Optimization Lab</div>
              {isOptimizing && <div className="text-xs text-yellow-500 animate-pulse font-bold">RUNNING PARAMETER SWEEP...</div>}
            </div>

            {optimizationResults?.best ? (
              <>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div className="bg-[#1c1c26] border border-[#2a2a35] rounded-lg p-3">
                    <div className="text-gray-500 text-[10px] uppercase tracking-wider mb-1">Best Score</div>
                    <div className="text-xl font-bold text-amber-400">{optimizationResults.best.score.toFixed(2)}</div>
                  </div>
                  <div className="bg-[#1c1c26] border border-[#2a2a35] rounded-lg p-3">
                    <div className="text-gray-500 text-[10px] uppercase tracking-wider mb-1">Best Return</div>
                    <div className={`text-xl font-bold ${optimizationResults.best.metrics.total_return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {formatPercent(optimizationResults.best.metrics.total_return_pct)}
                    </div>
                  </div>
                  <div className="bg-[#1c1c26] border border-[#2a2a35] rounded-lg p-3">
                    <div className="text-gray-500 text-[10px] uppercase tracking-wider mb-1">Best Drawdown</div>
                    <div className="text-xl font-bold text-red-400">
                      {formatPercent(optimizationResults.best.metrics.max_drawdown_pct)}
                    </div>
                  </div>
                  <div className="bg-[#1c1c26] border border-[#2a2a35] rounded-lg p-3">
                    <div className="text-gray-500 text-[10px] uppercase tracking-wider mb-1">Win Rate</div>
                    <div className="text-xl font-bold text-sky-400">
                      {optimizationResults.best.metrics.win_rate_pct.toFixed(1)}%
                    </div>
                  </div>
                </div>

                <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-[10px] uppercase tracking-widest text-gray-500">Best Parameters</div>
                      <div className="text-white mt-1">{Object.entries(optimizationResults.best.params).map(([key, value]) => `${key}: ${value}`).join(' | ')}</div>
                    </div>
                    <button onClick={() => applyOptimizedCode(optimizationResults.best.code)} className="px-3 py-2 text-xs font-semibold rounded-lg bg-amber-600 text-white hover:bg-amber-500 transition-colors">
                      Apply Best
                    </button>
                  </div>
                </div>

                <div className="bg-[#16161e] border border-[#2a2a35] rounded overflow-hidden">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="bg-[#2a2a35]/30 text-gray-500 text-[10px]">
                        <th className="p-2 border-b border-[#2a2a35]">Rank</th>
                        <th className="p-2 border-b border-[#2a2a35]">Params</th>
                        <th className="p-2 border-b border-[#2a2a35]">Return</th>
                        <th className="p-2 border-b border-[#2a2a35]">Drawdown</th>
                        <th className="p-2 border-b border-[#2a2a35]">Score</th>
                        <th className="p-2 border-b border-[#2a2a35]">Action</th>
                      </tr>
                    </thead>
                    <tbody className="text-[10px]">
                      {optimizationResults.results.map((result: OptimizationCandidate, index: number) => (
                        <tr key={index} className="border-b border-[#2a2a35]/50 hover:bg-white/5 transition-colors">
                          <td className="p-2 text-white font-bold">#{index + 1}</td>
                          <td className="p-2 text-gray-300">{Object.entries(result.params).map(([key, value]) => `${key}:${value}`).join(', ')}</td>
                          <td className={`p-2 font-bold ${result.metrics.total_return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>{formatPercent(result.metrics.total_return_pct)}</td>
                          <td className="p-2 text-red-400">{formatPercent(result.metrics.max_drawdown_pct)}</td>
                          <td className="p-2 text-amber-400 font-bold">{result.score.toFixed(2)}</td>
                          <td className="p-2">
                            <button onClick={() => applyOptimizedCode(result.code)} className="px-2 py-1 rounded bg-[#a55eea] text-white hover:bg-[#b87ef7] transition-colors">
                              Use
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                  <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-3">
                    <div className="text-[10px] uppercase tracking-widest text-gray-500 mb-3">Return Comparison</div>
                    <div className="space-y-2">
                      {optimizationResults.results.slice(0, 5).map((result: OptimizationCandidate, index: number, list: OptimizationCandidate[]) => (
                        <div key={index} className="space-y-1">
                          <div className="flex items-center justify-between text-[10px]">
                            <span className="text-gray-400">#{index + 1}</span>
                            <span className={result.metrics.total_return_pct >= 0 ? 'text-green-400 font-bold' : 'text-red-400 font-bold'}>
                              {formatPercent(result.metrics.total_return_pct)}
                            </span>
                          </div>
                          <div className="h-2 rounded-full bg-[#0d0d11] overflow-hidden">
                            <div
                              className={`h-full rounded-full ${result.metrics.total_return_pct >= 0 ? 'bg-green-500' : 'bg-red-500'}`}
                              style={{ width: getNormalizedBarWidth(result.metrics.total_return_pct, list.map((entry) => entry.metrics.total_return_pct)) }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-3">
                    <div className="text-[10px] uppercase tracking-widest text-gray-500 mb-3">Drawdown Comparison</div>
                    <div className="space-y-2">
                      {optimizationResults.results.slice(0, 5).map((result: OptimizationCandidate, index: number, list: OptimizationCandidate[]) => (
                        <div key={index} className="space-y-1">
                          <div className="flex items-center justify-between text-[10px]">
                            <span className="text-gray-400">#{index + 1}</span>
                            <span className="text-red-400 font-bold">{formatPercent(result.metrics.max_drawdown_pct)}</span>
                          </div>
                          <div className="h-2 rounded-full bg-[#0d0d11] overflow-hidden">
                            <div
                              className="h-full rounded-full bg-red-500"
                              style={{ width: getNormalizedBarWidth(result.metrics.max_drawdown_pct, list.map((entry) => entry.metrics.max_drawdown_pct)) }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-3">
                  <div className="flex items-center justify-between mb-3">
                    <div className="text-[10px] uppercase tracking-widest text-gray-500">Optimization History</div>
                    <div className="text-[10px] text-gray-600">{optimizationHistory.length} runs saved</div>
                  </div>
                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
                    {optimizationHistory.map((run) => (
                      <button
                        key={run.id}
                        onClick={() => {
                          setOptimizationResults(run);
                          if (run.best?.code) {
                            setStrategyCode(run.best.code);
                          }
                        }}
                        className="text-left bg-[#111118] border border-[#2a2a35] rounded-lg p-3 hover:border-[#a55eea] transition-colors"
                      >
                        <div className="flex items-center justify-between">
                          <div className="text-xs font-bold text-white">{run.label}</div>
                          <div className="text-[10px] text-gray-500">{run.timestamp}</div>
                        </div>
                        <div className="mt-2 text-[10px] text-gray-400">
                          Best return: <span className={run.best?.metrics?.total_return_pct >= 0 ? 'text-green-400' : 'text-red-400'}>{formatPercent(run.best?.metrics?.total_return_pct)}</span>
                        </div>
                        <div className="text-[10px] text-gray-500 mt-1">
                          Drawdown: {formatPercent(run.best?.metrics?.max_drawdown_pct)} | Win rate: {(run.best?.metrics?.win_rate_pct || 0).toFixed(1)}%
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              </>
            ) : !isOptimizing && (
              <div className="flex flex-col items-center justify-center py-10 text-gray-500 bg-[#16161e] border border-dashed border-[#2a2a35] rounded-lg">
                <span className="text-lg mb-2">Optimizer ready</span>
                <p>No optimization runs yet.</p>
                <p className="text-[10px]">Choose a strategy family and click "Optimize" to rank parameter combinations.</p>
              </div>
            )}
          </div>
        )}

        {activeTab === 'positions' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between px-1">
              <div className="text-gray-400 font-bold">Paper Portfolio (Live)</div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => void fetchTradeHistory(executionMode === 'live')}
                  disabled={isRefreshingTradeHistory}
                  className="px-2 py-1 rounded bg-[#1c1c24] text-[10px] text-gray-300 hover:text-white border border-[#2a2a35] disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {isRefreshingTradeHistory ? 'Refreshing...' : 'Refresh Status'}
                </button>
                <button
                  onClick={() => void fetchOpenOrders()}
                  disabled={isRefreshingOpenOrders}
                  className="px-2 py-1 rounded bg-[#1c1c24] text-[10px] text-gray-300 hover:text-white border border-[#2a2a35] disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {isRefreshingOpenOrders ? 'Loading Orders...' : 'Open Orders'}
                </button>
                <button
                  onClick={() => void fetchBrokerPositions()}
                  disabled={isRefreshingPositions}
                  className="px-2 py-1 rounded bg-[#1c1c24] text-[10px] text-gray-300 hover:text-white border border-[#2a2a35] disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {isRefreshingPositions ? 'Loading Positions...' : 'Broker Positions'}
                </button>
                <span className={`w-2 h-2 rounded-full ${isLiveTrading ? 'bg-green-500 animate-pulse' : 'bg-gray-600'}`}></span>
                <span className="text-[10px] text-gray-500">{isLiveTrading ? 'RUNNING' : 'IDLE'}</span>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-3">
                <div className="text-[10px] uppercase tracking-widest text-gray-500">Cash / Buying Power</div>
                <div className="text-lg font-bold text-white mt-1">
                  ${brokerPortfolioSummary.cashLikeBalance.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                </div>
              </div>
              <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-3">
                <div className="text-[10px] uppercase tracking-widest text-gray-500">Market Value</div>
                <div className="text-lg font-bold text-sky-300 mt-1">
                  ${brokerPortfolioSummary.marketValue.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                </div>
              </div>
              <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-3">
                <div className="text-[10px] uppercase tracking-widest text-gray-500">Unrealized P/L</div>
                <div className={`text-lg font-bold mt-1 ${brokerPortfolioSummary.unrealizedPl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  ${brokerPortfolioSummary.unrealizedPl.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                </div>
              </div>
              <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-3">
                <div className="text-[10px] uppercase tracking-widest text-gray-500">Exposure</div>
                <div className="text-lg font-bold text-white mt-1">
                  {brokerPortfolioSummary.positionCount} positions / {brokerPortfolioSummary.openOrderCount} open orders
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-3">
                <div className="text-[10px] uppercase tracking-widest text-gray-500">Winning Symbols</div>
                <div className="text-lg font-bold text-emerald-400 mt-1">{executionAnalytics.winningSymbols}</div>
              </div>
              <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-3">
                <div className="text-[10px] uppercase tracking-widest text-gray-500">Losing Symbols</div>
                <div className="text-lg font-bold text-red-400 mt-1">{executionAnalytics.losingSymbols}</div>
              </div>
              <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-3">
                <div className="text-[10px] uppercase tracking-widest text-gray-500">Closed Symbols</div>
                <div className="text-lg font-bold text-sky-300 mt-1">{executionAnalytics.closedSymbols}</div>
              </div>
              <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-3">
                <div className="text-[10px] uppercase tracking-widest text-gray-500">Avg Hold</div>
                <div className="text-lg font-bold text-white mt-1">
                  {executionAnalytics.avgHoldHours > 0 ? `${executionAnalytics.avgHoldHours.toFixed(1)}h` : '-'}
                </div>
              </div>
            </div>

            <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-3">
              <div className="flex items-center justify-between mb-3">
                <div className="text-[10px] uppercase tracking-widest text-gray-500">Execution Summary</div>
                <div className="text-[10px] text-gray-600">{executionSummaryRows.length} symbols</div>
              </div>
              {executionSummaryRows.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="bg-[#2a2a35]/30 text-gray-500 text-[10px]">
                        <th className="p-2 border-b border-[#2a2a35]">Symbol</th>
                        <th className="p-2 border-b border-[#2a2a35]">Status</th>
                        <th className="p-2 border-b border-[#2a2a35]">Trades</th>
                        <th className="p-2 border-b border-[#2a2a35]">Net Qty</th>
                        <th className="p-2 border-b border-[#2a2a35]">Avg Entry</th>
                        <th className="p-2 border-b border-[#2a2a35]">Win Rate</th>
                        <th className="p-2 border-b border-[#2a2a35]">Avg Return</th>
                        <th className="p-2 border-b border-[#2a2a35]">Realized</th>
                        <th className="p-2 border-b border-[#2a2a35]">Unrealized</th>
                        <th className="p-2 border-b border-[#2a2a35]">Open Orders</th>
                      </tr>
                    </thead>
                    <tbody className="text-[10px]">
                      {executionSummaryRows.map((row) => (
                        <tr key={row.symbol} className="border-b border-[#2a2a35]/50 hover:bg-white/5 transition-colors">
                          <td className="p-2 text-white font-bold">{row.symbol}</td>
                          <td className={`p-2 font-bold ${
                            row.status === 'active'
                              ? 'text-amber-300'
                              : row.status === 'held'
                                ? 'text-sky-300'
                                : 'text-gray-400'
                          }`}>
                            {row.status}
                          </td>
                          <td className="p-2 text-gray-300">{row.tradeCount}</td>
                          <td className="p-2 text-gray-400">{row.netQty.toFixed(4)}</td>
                          <td className="p-2 text-gray-400">{row.avgEntry > 0 ? `$${row.avgEntry.toLocaleString(undefined, { maximumFractionDigits: 4 })}` : '-'}</td>
                          <td className="p-2 text-sky-300">{row.winRate > 0 ? `${row.winRate.toFixed(1)}%` : '-'}</td>
                          <td className={`p-2 ${row.avgClosedReturn >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                            {row.avgClosedReturn !== 0 ? `${row.avgClosedReturn.toFixed(2)}%` : '-'}
                          </td>
                          <td className={`p-2 ${row.realizedPl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                            ${row.realizedPl.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                          </td>
                          <td className={`p-2 ${row.unrealizedPl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                            ${row.unrealizedPl.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                          </td>
                          <td className="p-2 text-gray-400">{row.openOrders}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-[10px] text-gray-500">No execution summary available yet for the current broker context.</div>
              )}
            </div>

            <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-3">
              <div className="flex items-center justify-between mb-3">
                <div className="text-[10px] uppercase tracking-widest text-gray-500">Broker Positions</div>
                <div className="text-[10px] text-gray-600">{brokerPositions.length} held</div>
              </div>
              {brokerPositions.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="bg-[#2a2a35]/30 text-gray-500 text-[10px]">
                        <th className="p-2 border-b border-[#2a2a35]">Symbol</th>
                        <th className="p-2 border-b border-[#2a2a35]">Side</th>
                        <th className="p-2 border-b border-[#2a2a35]">Qty</th>
                        <th className="p-2 border-b border-[#2a2a35]">Available</th>
                        <th className="p-2 border-b border-[#2a2a35]">Avg Entry</th>
                        <th className="p-2 border-b border-[#2a2a35]">Market Value</th>
                        <th className="p-2 border-b border-[#2a2a35]">Unrealized P/L</th>
                      </tr>
                    </thead>
                    <tbody className="text-[10px]">
                      {brokerPositions.map((position) => (
                        <tr key={`${position.symbol}-${position.side}`} className="border-b border-[#2a2a35]/50 hover:bg-white/5 transition-colors">
                          <td className="p-2 text-white font-bold">{position.symbol}</td>
                          <td className="p-2 text-sky-300">{position.side}</td>
                          <td className="p-2 text-gray-300">{position.qty}</td>
                          <td className="p-2 text-gray-400">
                            {position.available_qty}
                            {position.locked_qty > 0 ? ` (${position.locked_qty} locked)` : ''}
                          </td>
                          <td className="p-2 text-gray-400">
                            {position.avg_entry_price !== null ? `$${position.avg_entry_price.toLocaleString()}` : '-'}
                          </td>
                          <td className="p-2 text-gray-400">
                            {position.market_value !== null ? `$${position.market_value.toLocaleString()}` : '-'}
                          </td>
                          <td className={`p-2 ${position.unrealized_pl !== null && position.unrealized_pl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                            {position.unrealized_pl !== null ? `$${position.unrealized_pl.toLocaleString()}` : '-'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-[10px] text-gray-500">No broker positions for the current symbol and broker.</div>
              )}
            </div>

            <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-3">
              <div className="flex items-center justify-between mb-3">
                <div className="text-[10px] uppercase tracking-widest text-gray-500">Broker Open Orders</div>
                <div className="text-[10px] text-gray-600">{brokerOpenOrders.length} exchange-side</div>
              </div>
              {brokerOpenOrders.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="bg-[#2a2a35]/30 text-gray-500 text-[10px]">
                        <th className="p-2 border-b border-[#2a2a35]">Order Id</th>
                        <th className="p-2 border-b border-[#2a2a35]">Side</th>
                        <th className="p-2 border-b border-[#2a2a35]">Status</th>
                        <th className="p-2 border-b border-[#2a2a35]">Type</th>
                        <th className="p-2 border-b border-[#2a2a35]">Price</th>
                        <th className="p-2 border-b border-[#2a2a35]">Orig Qty</th>
                        <th className="p-2 border-b border-[#2a2a35]">Executed</th>
                      </tr>
                    </thead>
                    <tbody className="text-[10px]">
                      {brokerOpenOrders.map((order) => (
                        <tr key={`${order.broker_order_id}-${order.time}`} className="border-b border-[#2a2a35]/50 hover:bg-white/5 transition-colors">
                          <td className="p-2 text-sky-300">{order.broker_order_id || '-'}</td>
                          <td className={`p-2 font-bold ${order.side === 'BUY' ? 'text-green-400' : 'text-red-400'}`}>{order.side}</td>
                          <td className="p-2 text-amber-300">{order.status}</td>
                          <td className="p-2 text-gray-400">{order.type}</td>
                          <td className="p-2 text-gray-300">{order.price ? `$${order.price.toLocaleString()}` : 'Market'}</td>
                          <td className="p-2 text-gray-400">{order.orig_qty}</td>
                          <td className="p-2 text-gray-500">{order.executed_qty}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-[10px] text-gray-500">No broker open orders for the current symbol and broker.</div>
              )}
            </div>

            <div className="flex flex-wrap gap-2">
              {[
                ['all', 'All'],
                ['open', 'Open'],
                ['filled', 'Filled'],
                ['tests', 'Tests'],
                ['issues', 'Issues'],
              ].map(([id, label]) => (
                <button
                  key={id}
                  onClick={() => setTradeHistoryFilter(id as 'all' | 'filled' | 'tests' | 'issues' | 'open')}
                  className={`px-2.5 py-1 rounded border text-[10px] transition-colors ${
                    tradeHistoryFilter === id
                      ? 'bg-sky-500/15 border-sky-500 text-sky-300'
                      : 'bg-[#111118] border-[#2a2a35] text-gray-400 hover:border-sky-500/40'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            {visibleTradeHistory.length > 0 ? (
              <div className="bg-[#16161e] border border-[#2a2a35] rounded overflow-hidden">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-[#2a2a35]/30 text-gray-500 text-[10px]">
                      <th className="p-2 border-b border-[#2a2a35]">Asset</th>
                      <th className="p-2 border-b border-[#2a2a35]">Side</th>
                      <th className="p-2 border-b border-[#2a2a35]">Broker</th>
                      <th className="p-2 border-b border-[#2a2a35]">Status</th>
                      <th className="p-2 border-b border-[#2a2a35]">Price</th>
                      <th className="p-2 border-b border-[#2a2a35]">Amount</th>
                      <th className="p-2 border-b border-[#2a2a35]">Time</th>
                      <th className="p-2 border-b border-[#2a2a35]">Action</th>
                    </tr>
                  </thead>
                  <tbody className="text-[10px]">
                    {visibleTradeHistory.map((trade: TradeRecord, index: number) => (
                      <tr key={index} className="border-b border-[#2a2a35]/50 hover:bg-white/5 transition-colors">
                        <td className="p-2 text-white font-bold">{trade.symbol}</td>
                        <td className={`p-2 font-bold ${trade.side === 'BUY' ? 'text-green-400' : 'text-red-400'}`}>{trade.side}</td>
                        <td className="p-2 text-sky-300">
                          {trade.broker_id || 'paper'} / {trade.execution_mode || 'paper'}
                          {trade.is_test ? ' [test]' : ''}
                        </td>
                        <td className="p-2">
                          {(() => {
                            const reason = getTradeReason(trade);
                            const progress = getTradeProgress(trade);
                            return (
                              <>
                          <div className={`font-bold ${
                            trade.order_status === 'filled' || trade.order_status === 'tested'
                              ? 'text-emerald-400'
                              : trade.order_status === 'rejected' || trade.order_status === 'expired'
                                ? 'text-red-400'
                                : 'text-amber-300'
                          }`}>
                            {trade.order_status || 'unknown'}
                          </div>
                          <div className="text-[9px] text-gray-500">
                            {trade.order_type || 'market'}
                            {trade.broker_order_id ? ` | #${trade.broker_order_id}` : ''}
                          </div>
                          {progress.executedQty > 0 && progress.originalQty > 0 && progress.fillProgressPct < 100 && (
                            <div className="text-[9px] text-amber-300">
                              Partial fill: {progress.executedQty}/{progress.originalQty} ({progress.fillProgressPct.toFixed(1)}%)
                            </div>
                          )}
                          {reason && (
                            <div className="text-[9px] text-red-300 max-w-[180px] truncate" title={reason}>
                              {reason}
                            </div>
                          )}
                              </>
                            );
                          })()}
                        </td>
                        <td className="p-2 text-gray-300">${trade.price.toLocaleString()}</td>
                        <td className="p-2 text-gray-400">{trade.qty}</td>
                        <td className="p-2 text-gray-500">{trade.timestamp}</td>
                        <td className="p-2">
                          {trade.id &&
                          trade.execution_mode === 'live' &&
                          !trade.is_test &&
                          !['filled', 'canceled', 'cancelled', 'rejected', 'expired', 'tested'].includes(trade.order_status || '') &&
                          trade.broker_order_id ? (
                            <button
                              onClick={() => void cancelTradeOrder(trade.id as number)}
                              disabled={isCancellingTradeId === trade.id}
                              className="px-2 py-1 rounded bg-red-700 text-white text-[10px] hover:bg-red-600 disabled:opacity-40 disabled:cursor-not-allowed"
                            >
                              {isCancellingTradeId === trade.id ? 'Cancelling...' : 'Cancel'}
                            </button>
                          ) : (
                            <span className="text-[9px] text-gray-600">-</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-6 text-gray-600 border border-dashed border-[#2a2a35] rounded">
                <p>No active trades recorded in this session.</p>
              </div>
            )}
          </div>
        )}

        {activeTab === 'logs' && (
          <div className="space-y-1 font-mono text-[10px]">
            {tradingLogs.length > 0 ? (
              tradingLogs.map((log, index) => {
                const isError = log.includes('ERROR');
                const isSignal = log.includes('SIGNAL');
                return (
                  <div key={index} className={isError ? 'text-red-400' : isSignal ? 'text-yellow-400 font-bold' : 'text-gray-400'}>
                    {log}
                  </div>
                );
              })
            ) : (
              <div className="text-gray-600 italic">Waiting for logs... Start Live Paper Trading to see activity.</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

