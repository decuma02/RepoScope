import sqlite3
from typing import Optional, List
from backend.app.schemas.api import GraphResponse, GraphNode, GraphEdge, RelationshipType

class GraphService:
    """
    Focused Graph Query Service.
    Produces 1-hop adjacency views centered on selected focus node or evidence sources.
    """

    @staticmethod
    def get_focused_graph(
        conn: sqlite3.Connection,
        repo_id: str,
        node_id: Optional[str] = None,
        source_ids: Optional[List[str]] = None
    ) -> GraphResponse:
        cursor = conn.cursor()

        cursor.execute("SELECT id, path, language FROM files WHERE repository_id = ?", (repo_id,))
        files = {f["id"]: f for f in cursor.fetchall()}

        if not files:
            return GraphResponse(focus=None, nodes=[], edges=[])

        target_file_id = node_id
        if not target_file_id and source_ids:
            clean_id = source_ids[0].replace("src_", "")
            if clean_id in files:
                target_file_id = clean_id

        if not target_file_id:
            target_file_id = list(files.keys())[0]

        cursor.execute(
            """
            SELECT * FROM relationships
            WHERE repository_id = ? AND (source_id = ? OR target_id = ?)
            """,
            (repo_id, target_file_id, target_file_id)
        )
        rel_rows = cursor.fetchall()

        nodes_map = {}
        edges = []

        focus_f = files.get(target_file_id)
        if focus_f:
            nodes_map[target_file_id] = GraphNode(
                id=target_file_id,
                type="file",
                label=focus_f["path"].split("/")[-1],
                path=focus_f["path"],
                selected=True
            )

        for r in rel_rows:
            src = r["source_id"]
            tgt = r["target_id"]

            if src in files and src not in nodes_map:
                nodes_map[src] = GraphNode(
                    id=src,
                    type="file",
                    label=files[src]["path"].split("/")[-1],
                    path=files[src]["path"],
                    selected=False
                )

            if tgt in files and tgt not in nodes_map:
                nodes_map[tgt] = GraphNode(
                    id=tgt,
                    type="file",
                    label=files[tgt]["path"].split("/")[-1],
                    path=files[tgt]["path"],
                    selected=False
                )

            edges.append(
                GraphEdge(
                    id=r["id"],
                    source=src,
                    target=tgt,
                    type=RelationshipType(r["type"]),
                    confidence=r["confidence"]
                )
            )

        focus_info = {"type": "file", "id": target_file_id} if focus_f else None

        return GraphResponse(
            focus=focus_info,
            nodes=list(nodes_map.values()),
            edges=edges
        )
