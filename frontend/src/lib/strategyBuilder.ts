type BuilderNode = {
  id: string;
  type?: string;
  data?: {
    label?: string;
    category?: string;
    payload?: {
      indicator?: string;
      side?: string;
      operator?: string;
      value?: number;
      fast?: number;
      slow?: number;
      signal?: number;
      period?: number;
      stopLoss?: number;
      takeProfit?: number;
      cooldown?: number;
      positionSize?: number;
    };
  };
};

type BuilderEdge = {
  source: string;
  target: string;
};

export type BuilderValidationResult = {
  valid: boolean;
  errors: string[];
  warnings: string[];
};

const findNodeByCategory = (nodes: BuilderNode[], category: string) =>
  nodes.find((node) => node.data?.category === category);

const hasEdge = (edges: BuilderEdge[], source: string, target: string) =>
  edges.some((edge) => edge.source === source && edge.target === target);

export const validateStrategyGraph = (nodes: BuilderNode[], edges: BuilderEdge[]): BuilderValidationResult => {
  const errors: string[] = [];
  const warnings: string[] = [];

  const entryNode = findNodeByCategory(nodes, 'entry');
  const indicatorNode = findNodeByCategory(nodes, 'indicator');
  const conditionNode = findNodeByCategory(nodes, 'condition');
  const actionNodes = nodes.filter((node) => node.data?.category === 'action');
  const riskNodes = nodes.filter((node) => node.data?.category === 'risk');

  if (!entryNode) {
    errors.push('A strategy flow must include a start node.');
  }
  if (!indicatorNode) {
    errors.push('Add at least one indicator node.');
  }
  if (!conditionNode) {
    errors.push('Add at least one condition node.');
  }
  if (actionNodes.length === 0) {
    errors.push('Add at least one BUY or SELL action node.');
  }

  if (indicatorNode && conditionNode && !hasEdge(edges, indicatorNode.id, conditionNode.id)) {
    errors.push('Connect an indicator node to a condition node.');
  }

  if (conditionNode) {
    const connectedActions = actionNodes.filter((node) => hasEdge(edges, conditionNode.id, node.id));
    if (connectedActions.length === 0) {
      errors.push('Connect a condition node to at least one action node.');
    }
    if (!connectedActions.some((node) => node.data?.payload?.side === 'buy')) {
      warnings.push('No BUY action is connected; the strategy may never open a position.');
    }
    if (!connectedActions.some((node) => node.data?.payload?.side === 'sell')) {
      warnings.push('No SELL action is connected; exits will rely only on risk controls.');
    }
  }

  if (riskNodes.length > 1) {
    warnings.push('Multiple risk blocks detected; only the first one will be used in local export.');
  }

  const riskNode = riskNodes[0];
  if (!riskNode) {
    warnings.push('No risk block found; local export will use default stop-loss, take-profit, cooldown, and position size values.');
  } else {
    const stopLoss = Number(riskNode.data?.payload?.stopLoss ?? 3);
    const takeProfit = Number(riskNode.data?.payload?.takeProfit ?? 6);
    const cooldown = Number(riskNode.data?.payload?.cooldown ?? 2);
    const positionSize = Number(riskNode.data?.payload?.positionSize ?? 50);

    if (!(stopLoss > 0)) {
      errors.push('Risk block stop-loss must be greater than 0.');
    }
    if (!(takeProfit > 0)) {
      errors.push('Risk block take-profit must be greater than 0.');
    }
    if (takeProfit <= stopLoss) {
      warnings.push('Take-profit is less than or equal to stop-loss; the risk/reward profile may be poor.');
    }
    if (cooldown < 0) {
      errors.push('Risk block cooldown must be zero or greater.');
    }
    if (positionSize <= 0 || positionSize > 100) {
      errors.push('Risk block position size must be between 1 and 100.');
    }
  }

  const connectedNodeIds = new Set<string>();
  edges.forEach((edge) => {
    connectedNodeIds.add(edge.source);
    connectedNodeIds.add(edge.target);
  });

  const disconnected = nodes.filter(
    (node) => node.data?.category !== 'entry' && !connectedNodeIds.has(node.id),
  );
  if (disconnected.length > 0) {
    warnings.push(`Disconnected nodes detected: ${disconnected.map((node) => node.data?.label || node.id).join(', ')}.`);
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
  };
};

const getIndicatorSnippet = (nodes: BuilderNode[]) => {
  const indicators = new Set(
    nodes
      .filter((node) => node.data?.category === 'indicator')
      .map((node) => node.data?.payload?.indicator)
      .filter(Boolean),
  );

  const snippets: string[] = [];

  if (indicators.has('sma')) {
    snippets.push("    df['sma_20'] = df['close'].rolling(20).mean()");
  }
  if (indicators.has('ema')) {
    snippets.push("    df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()");
  }
  if (indicators.has('rsi')) {
    snippets.push("    delta = df['close'].diff()");
    snippets.push("    gain = delta.clip(lower=0).rolling(14).mean()");
    snippets.push("    loss = (-delta.clip(upper=0)).rolling(14).mean()");
    snippets.push("    rs = gain / loss.replace(0, pd.NA)");
    snippets.push("    df['rsi_14'] = 100 - (100 / (1 + rs))");
  }
  if (indicators.has('macd')) {
    snippets.push("    df['ema_fast_12'] = df['close'].ewm(span=12, adjust=False).mean()");
    snippets.push("    df['ema_slow_26'] = df['close'].ewm(span=26, adjust=False).mean()");
    snippets.push("    df['macd'] = df['ema_fast_12'] - df['ema_slow_26']");
    snippets.push("    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()");
  }

  return snippets;
};

const getConditionExpression = (nodes: BuilderNode[], edges: BuilderEdge[]) => {
  const conditionNode = findNodeByCategory(nodes, 'condition');
  const indicatorNode = findNodeByCategory(nodes, 'indicator');
  const actionNode = findNodeByCategory(nodes, 'action');

  if (!conditionNode || !indicatorNode || !actionNode) {
    return null;
  }

  const connected = edges.some(
    (edge) =>
      edge.source === indicatorNode.id &&
      edge.target === conditionNode.id,
  ) && edges.some(
    (edge) =>
      edge.source === conditionNode.id &&
      edge.target === actionNode.id,
  );

  const indicator = indicatorNode.data?.payload?.indicator;
  const side = actionNode.data?.payload?.side ?? 'buy';
  const operator = conditionNode.data?.payload?.operator ?? 'lt';
  const value = conditionNode.data?.payload?.value ?? 30;

  if (!connected || !indicator) {
    return null;
  }

  const columnByIndicator: Record<string, string> = {
    sma: "df['close'] - df['sma_20']",
    ema: "df['close'] - df['ema_21']",
    rsi: "df['rsi_14']",
    macd: "df['macd'] - df['macd_signal']",
  };

  const indicatorExpr = columnByIndicator[indicator] ?? "df['close']";

  if (indicator === 'macd') {
    return side === 'buy'
      ? `${indicatorExpr} > 0`
      : `${indicatorExpr} < 0`;
  }

  const opMap: Record<string, string> = {
    lt: '<',
    lte: '<=',
    gt: '>',
    gte: '>=',
  };

  const comparison = `${indicatorExpr} ${opMap[operator] ?? '<'} ${value}`;
  return side === 'buy' ? comparison : comparison;
};

const getRiskPayload = (nodes: BuilderNode[]) => {
  const riskNode = findNodeByCategory(nodes, 'risk');
  return {
    stopLoss: Number(riskNode?.data?.payload?.stopLoss ?? 3),
    takeProfit: Number(riskNode?.data?.payload?.takeProfit ?? 6),
    cooldown: Number(riskNode?.data?.payload?.cooldown ?? 2),
    positionSize: Number(riskNode?.data?.payload?.positionSize ?? 50),
  };
};

export const buildStrategyCodeFromGraph = (nodes: BuilderNode[], edges: BuilderEdge[]) => {
  const indicatorLines = getIndicatorSnippet(nodes);
  const buyRule = getConditionExpression(nodes, edges) ?? "df['rsi_14'] < 30";
  const sellRule = buyRule.includes("rsi_14")
    ? "df['rsi_14'] > 70"
    : buyRule.includes("macd")
      ? "(df['macd'] - df['macd_signal']) < 0"
      : "df['close'] < df['ema_21']";
  const risk = getRiskPayload(nodes);

  return `# Strategy exported from Astral AI Visual Builder
# pd is supplied by Astral's restricted strategy runtime.
def strategy(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
${indicatorLines.length > 0 ? indicatorLines.join('\n') : "    df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()\n    delta = df['close'].diff()\n    gain = delta.clip(lower=0).rolling(14).mean()\n    loss = (-delta.clip(upper=0)).rolling(14).mean()\n    rs = gain / loss.replace(0, pd.NA)\n    df['rsi_14'] = 100 - (100 / (1 + rs))"}

    df['signal'] = 0
    df.loc[${buyRule}, 'signal'] = 1
    df.loc[${sellRule}, 'signal'] = -1
    df['signal'] = df['signal'].fillna(0)
    df['position_size_pct'] = ${risk.positionSize}

    in_position = False
    cooldown_remaining = 0
    entry_price = 0.0

    for idx in range(len(df)):
        current_price = float(df['close'].iloc[idx])
        raw_signal = int(df['signal'].iloc[idx])

        if cooldown_remaining > 0:
            cooldown_remaining -= 1
            if not in_position:
                df.iloc[idx, df.columns.get_loc('signal')] = 0
                continue

        if in_position:
            stop_level = entry_price * (1 - ${risk.stopLoss} / 100)
            take_level = entry_price * (1 + ${risk.takeProfit} / 100)
            if current_price <= stop_level or current_price >= take_level:
                df.iloc[idx, df.columns.get_loc('signal')] = -1
                in_position = False
                cooldown_remaining = ${risk.cooldown}
                continue

        if raw_signal == 1 and not in_position:
            entry_price = current_price
            in_position = True
        elif raw_signal == -1 and in_position:
            in_position = False
            cooldown_remaining = ${risk.cooldown}

    return df
`;
};
