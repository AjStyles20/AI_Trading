import { useCallback, useEffect, useState } from 'react';
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  addEdge,
  type Connection,
  type Edge,
  type Node,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import axios from 'axios';
import { buildStrategyCodeFromGraph, validateStrategyGraph } from '../lib/strategyBuilder';

export type BuilderNodeData = {
  label?: string;
  category?: string;
  payload?: Record<string, number | string>;
};

export type BuilderNode = Node<BuilderNodeData>;

export type StrategyBuilderGraph = {
  nodes: BuilderNode[];
  edges: Edge[];
};

const initialNodes: BuilderNode[] = [
  {
    id: '1',
    type: 'input',
    data: { label: 'Start Strategy', category: 'entry' },
    position: { x: 250, y: 25 },
    className: 'bg-[#1c1c24] text-white border border-[#a55eea] rounded-lg p-2 font-bold text-xs',
  },
];

const initialEdges: Edge[] = [];

type NodeCategory = 'indicator' | 'condition' | 'action' | 'ml' | 'risk';

type StrategyBuilderProps = {
  setStrategyCode?: (c: string) => void;
  initialGraph?: StrategyBuilderGraph;
  onGraphChange?: (graph: StrategyBuilderGraph) => void;
};

export default function StrategyBuilder({ setStrategyCode, initialGraph, onGraphChange }: StrategyBuilderProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState<BuilderNode>(initialGraph?.nodes?.length ? initialGraph.nodes : initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialGraph?.edges?.length ? initialGraph.edges : initialEdges);
  const [validationMessages, setValidationMessages] = useState<{ errors: string[]; warnings: string[] }>({
    errors: [],
    warnings: [],
  });

  const syncGraph = useCallback((nextNodes: BuilderNode[], nextEdges: Edge[]) => {
    if (onGraphChange) {
      onGraphChange({ nodes: nextNodes, edges: nextEdges });
    }
  }, [onGraphChange]);

  useEffect(() => {
    syncGraph(nodes, edges);
  }, [nodes, edges, syncGraph]);

  const onConnect = useCallback((params: Edge | Connection) => {
    setEdges((currentEdges) => {
      const nextEdges = addEdge(params, currentEdges);
      syncGraph(nodes, nextEdges);
      return nextEdges;
    });
  }, [nodes, setEdges, syncGraph]);

  const addNode = (
    type: string,
    label: string,
    category: NodeCategory,
    payload: Record<string, number | string>,
  ) => {
    const newNode: BuilderNode = {
      id: (nodes.length + 1).toString(),
      data: { label: `${label} (${type})`, category, payload },
      position: { x: Math.random() * 240 + 100, y: Math.random() * 220 + 100 },
      className: 'bg-[#1c1c24] text-white border border-[#2a2a35] rounded-lg p-3 text-xs w-[170px] shadow-lg',
    };
    setNodes((currentNodes) => {
      const nextNodes = currentNodes.concat(newNode);
      syncGraph(nextNodes, edges);
      return nextNodes;
    });
  };

  const exportLocalCode = () => {
    const validation = validateStrategyGraph(nodes, edges);
    setValidationMessages({ errors: validation.errors, warnings: validation.warnings });
    if (!validation.valid) {
      alert(`Cannot export strategy yet:\n- ${validation.errors.join('\n- ')}`);
      return;
    }
    if (setStrategyCode) {
      setStrategyCode(buildStrategyCodeFromGraph(nodes, edges));
    }
  };

  const generateCode = async () => {
    const validation = validateStrategyGraph(nodes, edges);
    setValidationMessages({ errors: validation.errors, warnings: validation.warnings });
    if (!validation.valid) {
      alert(`Fix the builder flow before AI export:\n- ${validation.errors.join('\n- ')}`);
      return;
    }

    const strategyNodes = nodes.map((node) => ({ id: node.id, type: node.data?.label || node.type }));
    const flowEdges = edges.map((edge) => ({ source: edge.source, target: edge.target }));

    if (setStrategyCode) {
      setStrategyCode('# Building strategy from visual flow...\n# Please wait...');
    }

    try {
      const res = await axios.post('http://127.0.0.1:8000/api/strategy/build', {
        nodes: strategyNodes,
        edges: flowEdges,
      });
      if (setStrategyCode) {
        setStrategyCode(res.data.code);
      }
      alert('Strategy generated. Check the Strategy Code tab in the bottom panel.');
    } catch (err) {
      console.error(err);
      exportLocalCode();
      alert('Backend generation is unavailable, so a local strategy draft has been exported instead.');
    }
  };

  return (
    <div className="flex flex-col h-full w-full bg-[#0a0a0c] text-white relative">
      <div className="flex flex-wrap gap-2 p-3 bg-[#121216] border-b border-[#2a2a35] z-10">
        <button onClick={() => addNode('indicator', 'RSI 14', 'indicator', { indicator: 'rsi', period: 14 })} className="px-3 py-1.5 bg-[#1c1c24] border border-[#2a2a35] text-xs font-semibold rounded hover:bg-[#2a2a35] transition-colors">
          + Add RSI
        </button>
        <button onClick={() => addNode('indicator', 'MACD 12/26/9', 'indicator', { indicator: 'macd', fast: 12, slow: 26, signal: 9 })} className="px-3 py-1.5 bg-[#1c1c24] border border-[#2a2a35] text-xs font-semibold rounded hover:bg-[#2a2a35] transition-colors">
          + Add MACD
        </button>
        <button onClick={() => addNode('indicator', 'SMA 20', 'indicator', { indicator: 'sma', period: 20 })} className="px-3 py-1.5 bg-[#1c1c24] border border-[#2a2a35] text-xs font-semibold rounded hover:bg-[#2a2a35] transition-colors">
          + Add SMA
        </button>
        <button onClick={() => addNode('indicator', 'EMA 21', 'indicator', { indicator: 'ema', period: 21 })} className="px-3 py-1.5 bg-[#1c1c24] border border-[#2a2a35] text-xs font-semibold rounded hover:bg-[#2a2a35] transition-colors">
          + Add EMA
        </button>
        <button onClick={() => addNode('condition', 'Below 30', 'condition', { operator: 'lt', value: 30 })} className="px-3 py-1.5 bg-[#1c1c24] border border-[#2a2a35] text-xs font-semibold rounded hover:bg-[#2a2a35] transition-colors text-yellow-500">
          + Condition {'<'} 30
        </button>
        <button onClick={() => addNode('condition', 'Above 70', 'condition', { operator: 'gt', value: 70 })} className="px-3 py-1.5 bg-[#1c1c24] border border-[#2a2a35] text-xs font-semibold rounded hover:bg-[#2a2a35] transition-colors text-yellow-500">
          + Condition {'>'} 70
        </button>
        <button onClick={() => addNode('action', 'BUY', 'action', { side: 'buy' })} className="px-3 py-1.5 bg-[#1c1c24] border border-[#2a2a35] text-xs font-semibold rounded hover:bg-[#2a2a35] transition-colors text-green-500">
          + Add BUY Action
        </button>
        <button onClick={() => addNode('action', 'SELL', 'action', { side: 'sell' })} className="px-3 py-1.5 bg-[#1c1c24] border border-[#2a2a35] text-xs font-semibold rounded hover:bg-[#2a2a35] transition-colors text-red-400">
          + Add SELL Action
        </button>
        <button onClick={() => addNode('risk', 'Risk 3/6/2/50', 'risk', { stopLoss: 3, takeProfit: 6, cooldown: 2, positionSize: 50 })} className="px-3 py-1.5 bg-[#10231b] border border-[#1f9d68] text-xs font-semibold rounded hover:bg-[#163127] transition-colors text-emerald-300">
          + Add Risk Block
        </button>
        <button onClick={() => addNode('ml', 'Model Signal', 'ml', { indicator: 'ml_signal' })} className="px-3 py-1.5 bg-[#a55eea]/20 border border-[#a55eea] text-xs font-semibold rounded hover:bg-[#a55eea]/40 transition-colors text-purple-300">
          + Add ML Signal
        </button>
        <button onClick={exportLocalCode} className="px-4 py-1.5 bg-[#1f6feb] text-xs font-bold rounded hover:bg-[#388bfd] transition-colors ml-auto">
          Local Export
        </button>
        <button onClick={generateCode} className="px-4 py-1.5 bg-blue-600 text-xs font-bold rounded hover:bg-blue-500 transition-colors">
          AI Export
        </button>
      </div>

      <div className="px-3 py-2 text-[11px] text-gray-400 border-b border-[#1b1b22] bg-[#0d0d11]">
        Connect indicator nodes into condition nodes, then route them into BUY or SELL actions. Add a risk block to embed stop-loss, take-profit, cooldown, and position sizing into local exports.
      </div>

      {(validationMessages.errors.length > 0 || validationMessages.warnings.length > 0) && (
        <div className="px-3 py-2 border-b border-[#1b1b22] bg-[#0d0d11] space-y-1">
          {validationMessages.errors.map((message, index) => (
            <div key={`error-${index}`} className="text-[11px] text-red-300">
              {message}
            </div>
          ))}
          {validationMessages.warnings.map((message, index) => (
            <div key={`warning-${index}`} className="text-[11px] text-amber-300">
              {message}
            </div>
          ))}
        </div>
      )}

      <div className="flex-1 w-full h-full">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          fitView
          className="bg-[#0a0a0c]"
          proOptions={{ hideAttribution: true }}
        >
          <Controls className="bg-[#1c1c24] border border-[#2a2a35] rounded overflow-hidden" />
          <MiniMap className="bg-[#1c1c24] border border-[#2a2a35] rounded" maskColor="#0f0f1388" />
          <Background color="#2a2a35" gap={16} />
        </ReactFlow>
      </div>
    </div>
  );
}
