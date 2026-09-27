"""
RelationshipIndex
=================
Simple deterministic query layer over the existing relationships table.

All methods accept an open sqlite3.Connection, return the existing
RelationshipDTO / RelationshipListResponse schemas, and perform no ranking.

Queries
-------
* get_outgoing(conn, repo_id, node_id)       – relationships where sourceId == node_id
* get_incoming(conn, repo_id, node_id)       – relationships where targetId == node_id
* get_neighbors(conn, repo_id, node_id)      – unique node IDs one hop away
* get_by_type(conn, repo_id, rel_type)       – all relationships of a specific type
* get_for_file(conn, repo_id, file_id)       – relationships that touch a file as source or target
"""

from __future__ import annotations

import sqlite3
from typing import List, Optional

from backend.app.models.domain import RelationshipType
from backend.app.schemas.api import RelationshipDTO, RelationshipListResponse, NeighborListResponse


# ---------------------------------------------------------------------------
# Internal row → DTO converter (shared by all queries)
# ---------------------------------------------------------------------------

def _row_to_dto(row: sqlite3.Row) -> RelationshipDTO:
    return RelationshipDTO(
        id=row["id"],
        repositoryId=row["repository_id"],
        sourceType=row["source_type"],
        sourceId=row["source_id"],
        targetType=row["target_type"],
        targetId=row["target_id"],
        type=RelationshipType(row["type"]),
        confidence=row["confidence"],
        sourceLine=row["source_line"],
        evidence=row["evidence"],
    )


def _fetch_relationships(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple,
) -> List[RelationshipDTO]:
    cursor = conn.cursor()
    cursor.execute(sql, params)
    return [_row_to_dto(r) for r in cursor.fetchall()]


# ---------------------------------------------------------------------------
# Public query methods
# ---------------------------------------------------------------------------

class RelationshipIndex:
    """Read-only query layer over the relationships table."""

    # 1. Outgoing relationships for a node
    @staticmethod
    def get_outgoing(
        conn: sqlite3.Connection,
        repo_id: str,
        node_id: str,
    ) -> RelationshipListResponse:
        """Return all relationships where sourceId equals *node_id*."""
        rels = _fetch_relationships(
            conn,
            "SELECT * FROM relationships WHERE repository_id = ? AND source_id = ?"
            " ORDER BY source_line, id",
            (repo_id, node_id),
        )
        return RelationshipListResponse(repositoryId=repo_id, relationships=rels)

    # 2. Incoming relationships for a node
    @staticmethod
    def get_incoming(
        conn: sqlite3.Connection,
        repo_id: str,
        node_id: str,
    ) -> RelationshipListResponse:
        """Return all relationships where targetId equals *node_id*."""
        rels = _fetch_relationships(
            conn,
            "SELECT * FROM relationships WHERE repository_id = ? AND target_id = ?"
            " ORDER BY source_line, id",
            (repo_id, node_id),
        )
        return RelationshipListResponse(repositoryId=repo_id, relationships=rels)

    # 3. One-hop neighbors
    @staticmethod
    def get_neighbors(
        conn: sqlite3.Connection,
        repo_id: str,
        node_id: str,
    ) -> NeighborListResponse:
        """Return unique node IDs directly connected to *node_id* (outgoing + incoming)."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT source_id, target_id
            FROM relationships
            WHERE repository_id = ? AND (source_id = ? OR target_id = ?)
            """,
            (repo_id, node_id, node_id),
        )
        neighbor_ids: list[str] = []
        seen: set[str] = set()
        for row in cursor.fetchall():
            for nid in (row["source_id"], row["target_id"]):
                if nid != node_id and nid not in seen:
                    seen.add(nid)
                    neighbor_ids.append(nid)
        neighbor_ids.sort()  # deterministic ordering
        return NeighborListResponse(repositoryId=repo_id, nodeId=node_id, neighborIds=neighbor_ids)

    # 4. Relationships by type
    @staticmethod
    def get_by_type(
        conn: sqlite3.Connection,
        repo_id: str,
        rel_type: RelationshipType,
    ) -> RelationshipListResponse:
        """Return all relationships of the given *rel_type*."""
        rels = _fetch_relationships(
            conn,
            "SELECT * FROM relationships WHERE repository_id = ? AND type = ?"
            " ORDER BY source_id, source_line, id",
            (repo_id, rel_type.value),
        )
        return RelationshipListResponse(repositoryId=repo_id, relationships=rels)

    # 5. Relationships for a file / component
    @staticmethod
    def get_for_file(
        conn: sqlite3.Connection,
        repo_id: str,
        file_id: str,
    ) -> RelationshipListResponse:
        """Return all relationships where source_id or target_id equals *file_id*."""
        rels = _fetch_relationships(
            conn,
            "SELECT * FROM relationships WHERE repository_id = ? AND (source_id = ? OR target_id = ?)"
            " ORDER BY source_line, id",
            (repo_id, file_id, file_id),
        )
        return RelationshipListResponse(repositoryId=repo_id, relationships=rels)
