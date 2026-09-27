import { useState } from "react";
import type { TreeNode } from "../../types/reposcope";
import { useWorkspace } from "../../context/WorkspaceContext";

function Node({ node, depth }: { node: TreeNode; depth: number }) {
  const { selectedFileId, setSelectedFileId, setTab, setGraphNodeId, setHighlight } = useWorkspace();
  const [open, setOpen] = useState(depth < 2);

  if (node.isDir) {
    return (
      <div className="tree-node">
        <button className="tree-row" style={{ paddingLeft: 10 + depth * 10 }} onClick={() => setOpen((v) => !v)}>
          {open ? "▾" : "▸"} {node.name}
        </button>
        {open && node.children?.length ? (
          <div className="tree-children">
            {node.children.map((child) => (
              <Node key={child.id} node={child} depth={depth + 1} />
            ))}
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <button
      className={`tree-row ${selectedFileId === node.id ? "active" : ""}`}
      style={{ paddingLeft: 10 + depth * 10 }}
      onClick={() => {
        setSelectedFileId(node.id);
        setGraphNodeId(node.id);
        setHighlight(undefined);
        setTab("code");
      }}
    >
      {node.name}
    </button>
  );
}

export function FileTree({ tree }: { tree: TreeNode[] }) {
  if (!tree.length) {
    return <p className="meta" style={{ padding: 14 }}>Analyze the repository to load its file tree.</p>;
  }
  return (
    <div>
      {tree.map((node) => (
        <Node key={node.id} node={node} depth={0} />
      ))}
    </div>
  );
}
