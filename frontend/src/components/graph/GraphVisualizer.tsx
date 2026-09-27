import { useEffect, useMemo, useState } from "react";
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
}

export function GraphVisualizer({ repositoryId }: { repositoryId: string }) {
  const { graphNodeId, graphSourceIds, setSelectedFileId, setTab, setGraphNodeId } = useWorkspace();
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  const layout = useMemo(() => layoutNodes(graph), [graph]);

  if (error) return <p className="error">{error}</p>;
  if (!graph) return <p className="meta" style={{ padding: 12 }}>Loading graph…</p>;
  if (!graph.nodes.length) {
    return <p className="meta" style={{ padding: 12 }}>No relationship graph yet. Analyze a repository first.</p>;
  }

  const width = 340;
  const height = 520;

  return (
    <div>
      <div className="legend">
        <span><i className="swatch" style={{ background: EDGE_COLOR.IMPORTS }} /> IMPORTS</span>
        <span><i className="swatch" style={{ background: EDGE_COLOR.EXPORTS }} /> EXPORTS</span>
        <span><i className="swatch" style={{ background: EDGE_COLOR.USES }} /> USES</span>
      </div>
      <svg className="graph-canvas" viewBox={`0 0 ${width} ${height}`}>
        {graph.edges.map((edge) => {
          const source = layout.get(edge.source);
          const target = layout.get(edge.target);
          if (!source || !target) return null;
          return (
            <line
              key={edge.id}
              x1={source.x}
              y1={source.y}
              x2={target.x}
              y2={target.y}
              stroke={EDGE_COLOR[edge.type] ?? "#98a2b3"}
              strokeWidth={1.6}
              opacity={0.85}
            />
          );
        })}
        {graph.nodes.map((node) => {
          const pos = layout.get(node.id);
          if (!pos) return null;
          const selected = node.selected || node.id === graphNodeId;
          return (
            <g
              key={node.id}
              transform={`translate(${pos.x}, ${pos.y})`}
              style={{ cursor: "pointer" }}
              onClick={() => {
                setGraphNodeId(node.id);
                setSelectedFileId(node.type === "file" ? node.id : undefined);
                setTab("code");
              }}
            >
              <circle
                r={selected ? 16 : 12}
                fill={node.type === "file" ? "#0f62fe" : "#33b1ff"}
                stroke={selected ? "#f2f4f8" : "transparent"}
                strokeWidth={2}
              />
              <text y={28} textAnchor="middle" fill="#f2f4f8" fontSize="11">
                {node.label}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function layoutNodes(graph: GraphData | null): Map<string, Positioned> {
  const map = new Map<string, Positioned>();
  if (!graph?.nodes.length) return map;
  const cx = 170;
  const cy = 250;
  const selected = graph.nodes.find((node) => node.selected) ?? graph.nodes[0];
  const others = graph.nodes.filter((node) => node.id !== selected.id);
  map.set(selected.id, { ...selected, x: cx, y: cy });
  const radius = Math.min(120, 40 + others.length * 18);
  others.forEach((node, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(others.length, 1) - Math.PI / 2;
    map.set(node.id, {
      ...node,
      x: cx + Math.cos(angle) * radius,
      y: cy + Math.sin(angle) * radius,
    });
  });
  return map;
}
