import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import type { HighlightRange } from "../types/reposcope";

export type WorkspaceTab = "graph" | "code" | "chat" | "search";

interface WorkspaceState {
  tab: WorkspaceTab;
  setTab: (tab: WorkspaceTab) => void;
  selectedFileId?: string;
  setSelectedFileId: (id?: string) => void;
  highlight?: HighlightRange;
  setHighlight: (range?: HighlightRange) => void;
  graphNodeId?: string;
  setGraphNodeId: (id?: string) => void;
  graphSourceIds: string[];
  setGraphSourceIds: (ids: string[]) => void;
  focusEvidence: (fileId: string, range?: HighlightRange, nodeIds?: string[]) => void;
}

const WorkspaceContext = createContext<WorkspaceState | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [tab, setTab] = useState<WorkspaceTab>("graph");
  const [selectedFileId, setSelectedFileId] = useState<string>();
  const [highlight, setHighlight] = useState<HighlightRange>();
  const [graphNodeId, setGraphNodeId] = useState<string>();
  const [graphSourceIds, setGraphSourceIds] = useState<string[]>([]);

  const value = useMemo<WorkspaceState>(
    () => ({
      tab,
      setTab,
      selectedFileId,
      setSelectedFileId,
      highlight,
      setHighlight,
      graphNodeId,
      setGraphNodeId,
      graphSourceIds,
      setGraphSourceIds,
      focusEvidence: (fileId, range, nodeIds) => {
        setSelectedFileId(fileId);
        setHighlight(range);
        setGraphNodeId(fileId);
        if (nodeIds?.length) setGraphSourceIds(nodeIds);
        setTab("code");
      },
    }),
    [tab, selectedFileId, highlight, graphNodeId, graphSourceIds],
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace() {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace must be used within WorkspaceProvider");
  return ctx;
}
