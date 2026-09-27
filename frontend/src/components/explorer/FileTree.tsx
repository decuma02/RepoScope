import { useState } from "react";
import type { TreeNode } from "../../types/reposcope";
import { useWorkspace } from "../../context/WorkspaceContext";

function getFileIcon(name: string, isDir: boolean, open?: boolean): string {
  if (isDir) {
    return open ? "📂" : "📁";
  }

  const lower = name.toLowerCase();
  const ext = lower.includes(".") ? lower.split(".").pop() || "" : "";

  if (lower === "dockerfile" || lower.startsWith("docker-compose")) return "🐳";
  if (lower === ".gitignore" || lower === ".gitattributes") return "🌿";
  if (lower === "package.json" || lower === "requirements.txt" || lower === "cargo.toml" || lower === "go.mod") return "📦";
  if (lower === ".env" || lower.endsWith(".env") || lower.endsWith(".env.example")) return "🔑";
  if (lower === "readme.md" || lower === "license") return "📜";

  switch (ext) {
    case "py":
    case "pyi":
    case "pyx":
      return "🐍";
    case "ts":
    case "tsx":
      return "🔷";
    case "js":
    case "jsx":
    case "mjs":
    case "cjs":
      return "🟨";
    case "css":
    case "scss":
    case "sass":
    case "less":
      return "🎨";
    case "html":
    case "htm":
      return "🌐";
    case "json":
    case "jsonc":
      return "⚙️";
    case "md":
    case "mdx":
      return "📝";
    case "yml":
    case "yaml":
      return "⚙️";
    case "sh":
    case "bash":
    case "zsh":
    case "ps1":
    case "bat":
      return "🐚";
    case "sql":
    case "db":
    case "sqlite":
      return "🗄️";
    case "rs":
      return "🦀";
    case "go":
      return "🐹";
    case "java":
    case "kt":
    case "scala":
      return "☕";
    case "c":
    case "cpp":
    case "h":
    case "hpp":
      return "⚙️";
    case "rb":
      return "💎";
    case "php":
      return "🐘";
    case "png":
    case "jpg":
    case "jpeg":
    case "gif":
    case "svg":
    case "ico":
      return "🖼️";
    default:
      return "📄";
  }
}

function Node({ node, depth }: { node: TreeNode; depth: number }) {
  const { selectedFileId, setSelectedFileId, setTab, setGraphNodeId, setHighlight } = useWorkspace();
  const [open, setOpen] = useState(depth < 2);

  const icon = getFileIcon(node.name, node.isDir, open);

  if (node.isDir) {
    return (
      <div className="tree-node">
        <button
          className="tree-row tree-dir"
          style={{ paddingLeft: 8 + depth * 10 }}
          onClick={() => setOpen((v) => !v)}
          title={node.path || node.name}
        >
          <span className="tree-caret">{open ? "▾" : "▸"}</span>
          <span className="tree-icon">{icon}</span>
          <span className="tree-label">{node.name}</span>
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

  const isSelected = selectedFileId === node.id;

  return (
    <button
      className={`tree-row tree-file ${isSelected ? "active" : ""}`}
      style={{ paddingLeft: 8 + depth * 10 }}
      onClick={() => {
        setSelectedFileId(node.id);
        setGraphNodeId(node.id);
        setHighlight(undefined);
        setTab("code");
      }}
      title={node.path || node.name}
    >
      <span className="tree-caret-placeholder" />
      <span className="tree-icon">{icon}</span>
      <span className="tree-label">{node.name}</span>
    </button>
  );
}

export function FileTree({ tree }: { tree: TreeNode[] }) {
  if (!tree.length) {
    return <p className="meta" style={{ padding: 14 }}>Analyze the repository to load its file tree.</p>;
  }
  return (
    <div className="tree-scroll">
      {tree.map((node) => (
        <Node key={node.id} node={node} depth={0} />
      ))}
    </div>
  );
}
