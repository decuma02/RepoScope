import { useEffect, useMemo, useState, useRef, useCallback } from "react";
import { getClient } from "../../api";
import { ApiError } from "../../api/client";
import { useWorkspace } from "../../context/WorkspaceContext";
import type { GraphData, GraphNode, RelationshipType } from "../../types/reposcope";

const EDGE_COLOR: Record<RelationshipType, string> = {
  IMPORTS: "#4589ff",
  EXPORTS: "#42be65",
  USES: "#ff832b",
};

interface Positioned extends GraphNode {
  x: number;
  y: number;
  ring: number;
}

export function GraphVisualizer({ repositoryId }: { repositoryId: string }) {
  const { graphNodeId, graphSourceIds, setSelectedFileId, setTab, setGraphNodeId } = useWorkspace();
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [error, setError] = useState<string | null>(null);

  // --- Browser Navigation History State ---
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState<number>(-1);

  // --- Pan & Zoom State ---
  const [scale, setScale] = useState<number>(1.0);
  const [pan, setPan] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const dragStartRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });

  // --- Fullscreen Expanded View State ---
  const [expanded, setExpanded] = useState<boolean>(false);

  // --- Sync Navigation History when graphNodeId changes ---
  useEffect(() => {
    if (!graphNodeId) return;
    setHistory((prev) => {
      if (prev[historyIndex] === graphNodeId) return prev;
      const nextHistory = prev.slice(0, historyIndex + 1);
      nextHistory.push(graphNodeId);
      setHistoryIndex(nextHistory.length - 1);
      return nextHistory;
    });
  }, [graphNodeId]);

  const handleGoBack = useCallback(() => {
    if (historyIndex > 0) {
      const prevId = history[historyIndex - 1];
      setHistoryIndex(historyIndex - 1);
      setGraphNodeId(prevId);
    }
  }, [historyIndex, history, setGraphNodeId]);

  const handleGoForward = useCallback(() => {
    if (historyIndex < history.length - 1) {
      const nextId = history[historyIndex + 1];
      setHistoryIndex(historyIndex + 1);
      setGraphNodeId(nextId);
    }
  }, [historyIndex, history, setGraphNodeId]);

  // --- Fetch Graph Data ---
  useEffect(() => {
    let cancelled = false;
    getClient()
      .getGraph(repositoryId, graphNodeId, graphSourceIds.length ? graphSourceIds : undefined)
      .then((data) => {
        if (!cancelled) {
          setGraph(data);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Graph failed to load.");
      });
    return () => {
      cancelled = true;
    };
  }, [repositoryId, graphNodeId, graphSourceIds]);

  // --- Reset Pan / Zoom ---
  const resetView = useCallback(() => {
    setScale(1.0);
    setPan({ x: 0, y: 0 });
  }, []);

  // --- Mouse Drag Pan Handlers ---
  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return; // Left click only
    setIsDragging(true);
    dragStartRef.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return;
    setPan({
      x: e.clientX - dragStartRef.current.x,
      y: e.clientY - dragStartRef.current.y,
    });
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  // --- Mouse Wheel Zoom Handler ---
  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.12 : 0.88;
    setScale((prev) => Math.min(3.5, Math.max(0.35, prev * zoomFactor)));
  };

  // --- Dimensions & Multi-Ring Layout Computation ---
  const dimensions = expanded ? { width: 1100, height: 750, cx: 550, cy: 375 } : { width: 440, height: 560, cx: 220, cy: 280 };

  const layout = useMemo(
    () => layoutMultiRing(graph, dimensions.cx, dimensions.cy, expanded),
    [graph, dimensions.cx, dimensions.cy, expanded]
  );

  if (error) return <p className="error">{error}</p>;
  if (!graph) return <p className="meta" style={{ padding: 12 }}>Loading graph graph…</p>;
  if (!graph.nodes.length) {
    return <p className="meta" style={{ padding: 12 }}>No relationship graph yet. Analyze a repository first.</p>;
  }

  const selectedNodeObj = graph.nodes.find((n) => n.id === graphNodeId) || graph.nodes.find((n) => n.selected);

  const renderContent = (isModal = false) => (
    <div className={`graph-visualizer-container ${isModal ? "is-modal" : ""}`}>
      {/* --- Top Control Bar (Browser Back/Forward + Initial View + Zoom + Fullscreen) --- */}
      <div className="graph-toolbar">
        <div className="toolbar-group history-controls">
          <button
            type="button"
            className="tool-btn"
            title="Reset to initial top connected graph"
            onClick={() => {
              setGraphNodeId(undefined);
              setHistory([]);
              setHistoryIndex(-1);
              resetView();
            }}
          >
            🏠 Initial View
          </button>
          <button
            type="button"
            className="tool-btn"
            title="Back to previous node"
            disabled={historyIndex <= 0}
            onClick={handleGoBack}
          >
            ← Back
          </button>
          <button
            type="button"
            className="tool-btn"
            title="Forward to next node"
            disabled={historyIndex >= history.length - 1}
            onClick={handleGoForward}
          >
            Forward →
          </button>
          {selectedNodeObj ? (
            <span className="current-node-badge" title={selectedNodeObj.path}>
              📍 {selectedNodeObj.label}
            </span>
          ) : null}
        </div>

        <div className="toolbar-group zoom-controls">
          <button
            type="button"
            className="tool-btn"
            title="Zoom In"
            onClick={() => setScale((s) => Math.min(3.5, s + 0.25))}
          >
            +
          </button>
          <span className="zoom-level">{Math.round(scale * 100)}%</span>
          <button
            type="button"
            className="tool-btn"
            title="Zoom Out"
            onClick={() => setScale((s) => Math.max(0.35, s - 0.25))}
          >
            −
          </button>
          <button type="button" className="tool-btn" title="Reset View" onClick={resetView}>
            ⟳ Reset
          </button>
          <button
            type="button"
            className="tool-btn highlight-btn"
            title={isModal ? "Minimize view" : "Expand Fullscreen view"}
            onClick={() => setExpanded(!expanded)}
          >
            {isModal ? "🗗 Minimize" : "⤢ Expand View"}
          </button>
        </div>
      </div>

      {/* --- Legend --- */}
      <div className="legend">
        <span><i className="swatch" style={{ background: EDGE_COLOR.IMPORTS }} /> IMPORTS ({graph.edges.filter(e => e.type === "IMPORTS").length})</span>
        <span><i className="swatch" style={{ background: EDGE_COLOR.EXPORTS }} /> EXPORTS ({graph.edges.filter(e => e.type === "EXPORTS").length})</span>
        <span><i className="swatch" style={{ background: EDGE_COLOR.USES }} /> USES ({graph.edges.filter(e => e.type === "USES").length})</span>
        <span className="nodes-count-tag">{graph.nodes.length} nodes connected</span>
      </div>

      {/* --- SVG Interactive Canvas --- */}
      <svg
        className={`graph-canvas ${isDragging ? "dragging" : ""}`}
        viewBox={`0 0 ${dimensions.width} ${dimensions.height}`}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onWheel={handleWheel}
      >
        <defs>
          <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>

        <g transform={`translate(${pan.x}, ${pan.y}) scale(${scale})`} transform-origin={`${dimensions.cx} ${dimensions.cy}`}>
          {/* Edges */}
          {graph.edges.map((edge) => {
            const source = layout.get(edge.source);
            const target = layout.get(edge.target);
            if (!source || !target) return null;
            return (
              <g key={edge.id}>
                <line
                  x1={source.x}
                  y1={source.y}
                  x2={target.x}
                  y2={target.y}
                  stroke={EDGE_COLOR[edge.type] ?? "#98a2b3"}
                  strokeWidth={edge.source === graphNodeId || edge.target === graphNodeId ? 2.2 : 1.4}
                  strokeDasharray={edge.type === "USES" ? "4,4" : undefined}
                  opacity={0.75}
                />
              </g>
            );
          })}

          {/* Nodes */}
          {graph.nodes.map((node) => {
            const pos = layout.get(node.id);
            if (!pos) return null;
            const selected = node.selected || node.id === graphNodeId;
            const isCenter = pos.ring === 0;

            // Label positioning to prevent overlap
            const isTop = pos.y < dimensions.cy;
            const labelY = isCenter ? 32 : isTop ? -20 : 28;

            return (
              <g
                key={node.id}
                transform={`translate(${pos.x}, ${pos.y})`}
                style={{ cursor: "pointer" }}
                onClick={(e) => {
                  e.stopPropagation();
                  setGraphNodeId(node.id);
                  setSelectedFileId(node.type === "file" ? node.id : undefined);
                  setTab("code");
                }}
              >
                {/* Glow ring behind selected node */}
                {selected ? (
                  <circle
                    r={isCenter ? 22 : 18}
                    fill="none"
                    stroke="#00ffff"
                    strokeWidth={3}
                    filter="url(#glow)"
                    opacity={0.9}
                  />
                ) : null}

                {/* Node Circle */}
                <circle
                  r={isCenter ? 18 : selected ? 15 : 12}
                  fill={isCenter ? "#4589ff" : node.type === "file" ? "#0f62fe" : "#33b1ff"}
                  stroke={selected ? "#ffffff" : "rgba(255,255,255,0.2)"}
                  strokeWidth={selected ? 2.5 : 1.5}
                />

                {/* Node Label background pill for crystal clear readability */}
                <rect
                  x={-Math.min(120, node.label.length * 4.2 + 8) / 2}
                  y={labelY - 12}
                  width={Math.min(120, node.label.length * 4.2 + 8)}
                  height={17}
                  rx={4}
                  fill={selected ? "rgba(15, 98, 254, 0.92)" : "rgba(11, 15, 22, 0.88)"}
                  stroke={selected ? "#00ffff" : "rgba(255,255,255,0.15)"}
                  strokeWidth={1}
                />

                {/* Label Text */}
                <text
                  y={labelY}
                  textAnchor="middle"
                  fill={selected ? "#ffffff" : "#e0e6ed"}
                  fontSize={selected ? "11.5" : "10.5"}
                  fontWeight={selected || isCenter ? "bold" : "normal"}
                >
                  <title>{node.path || node.label}</title>
                  {truncateLabel(node.label, isModal ? 24 : 16)}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );

  return (
    <>
      {renderContent(false)}

      {/* Fullscreen Expanded View Modal */}
      {expanded ? (
        <div className="graph-modal-overlay" onClick={() => setExpanded(false)}>
          <div className="graph-modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="graph-modal-header">
              <h3>🔍 Expanded Focused Relationship Graph</h3>
              <button type="button" className="close-btn" onClick={() => setExpanded(false)}>
                ✕
              </button>
            </div>
            <div className="graph-modal-body">{renderContent(true)}</div>
          </div>
        </div>
      ) : null}
    </>
  );
}

// --- Multi-Ring Staggered Concentric Layout Algorithm ---
function layoutMultiRing(
  graph: GraphData | null,
  cx: number,
  cy: number,
  isExpanded: boolean
): Map<string, Positioned> {
  const map = new Map<string, Positioned>();
  if (!graph?.nodes.length) return map;

  const selected = graph.nodes.find((node) => node.selected) ?? graph.nodes[0];
  const others = graph.nodes.filter((node) => node.id !== selected.id);

  // Ring 0: Focus Center Node
  map.set(selected.id, { ...selected, x: cx, y: cy, ring: 0 });

  if (!others.length) return map;

  // Concentric Ring Radii
  const r1 = isExpanded ? 200 : 120;
  const r2 = isExpanded ? 340 : 210;
  const r3 = isExpanded ? 460 : 285;

  // Split others across 3 concentric rings to avoid text collisions
  const ring1Nodes = others.slice(0, 8);
  const ring2Nodes = others.slice(8, 20);
  const ring3Nodes = others.slice(20);

  // Helper to place nodes evenly on a ring with rotational offset
  const placeRing = (nodes: GraphNode[], radius: number, ringIdx: number, angleOffset: number) => {
    const count = nodes.length;
    nodes.forEach((node, index) => {
      const angle = (Math.PI * 2 * index) / Math.max(count, 1) - Math.PI / 2 + angleOffset;
      map.set(node.id, {
        ...node,
        x: cx + Math.cos(angle) * radius,
        y: cy + Math.sin(angle) * radius,
        ring: ringIdx,
      });
    });
  };

  placeRing(ring1Nodes, r1, 1, 0);
  placeRing(ring2Nodes, r2, 2, Math.PI / 8); // Stagger by 22.5 deg
  placeRing(ring3Nodes, r3, 3, Math.PI / 4); // Stagger by 45 deg

  return map;
}

function truncateLabel(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.substring(0, maxLength - 2) + "…";
}
