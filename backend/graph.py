"""
AEGIS PoC — In-Memory Knowledge Graph
Architecture v2: Per-investigation scoping, cross-case intelligence views.
"""

from __future__ import annotations
from models import (
    GraphNode, GraphEdge, EntityType, DetectedEntity,
    EvidenceItem, EvidenceMetadata, GPSCoordinate
)
import state


def _find_node_by_label(label: str, investigation_id: str) -> GraphNode | None:
    """Find an existing node by label within an investigation (simple entity resolution)."""
    label_lower = label.lower().strip()
    for node in state.graph_nodes.values():
        if node.investigation_id == investigation_id and node.label.lower().strip() == label_lower:
            return node
    return None


def add_entity_node(
    entity: DetectedEntity,
    evidence_id: str,
    investigation_id: str,
    properties: dict | None = None,
) -> GraphNode:
    """Add an entity as a graph node, or return existing if label matches within investigation."""
    existing = _find_node_by_label(entity.description, investigation_id)
    if existing:
        if evidence_id not in existing.evidence_ids:
            existing.evidence_ids.append(evidence_id)
        existing.confidence = max(existing.confidence, entity.confidence)
        return existing

    node = GraphNode(
        investigation_id=investigation_id,
        type=entity.type,
        label=entity.description,
        properties=properties or {"details": entity.details},
        confidence=entity.confidence,
        evidence_ids=[evidence_id],
    )
    state.graph_nodes[node.id] = node
    return node


def add_evidence_node(ev: EvidenceItem) -> GraphNode:
    """Add an evidence item as a graph node."""
    existing = _find_node_by_label(ev.filename, ev.investigation_id)
    if existing:
        return existing

    node = GraphNode(
        investigation_id=ev.investigation_id,
        type=EntityType.DOCUMENT,
        label=ev.filename,
        properties={
            "mime_type": ev.mime_type,
            "sha256": ev.sha256[:16] + "...",
            "uploaded_at": ev.uploaded_at,
        },
        confidence=1.0,
        evidence_ids=[ev.id],
    )
    state.graph_nodes[node.id] = node
    return node


def add_location_node(gps: GPSCoordinate, label: str, evidence_id: str, investigation_id: str) -> GraphNode:
    """Add a GPS location as a graph node."""
    loc_label = label or f"{gps.latitude:.4f}, {gps.longitude:.4f}"
    existing = _find_node_by_label(loc_label, investigation_id)
    if existing:
        if evidence_id not in existing.evidence_ids:
            existing.evidence_ids.append(evidence_id)
        return existing

    node = GraphNode(
        investigation_id=investigation_id,
        type=EntityType.LOCATION,
        label=loc_label,
        properties={
            "latitude": gps.latitude,
            "longitude": gps.longitude,
            "altitude": gps.altitude,
        },
        confidence=1.0,
        evidence_ids=[evidence_id],
    )
    state.graph_nodes[node.id] = node
    return node


def add_edge(
    source_id: str,
    target_id: str,
    relationship: str,
    investigation_id: str,
    confidence: float = 1.0,
    properties: dict | None = None,
) -> GraphEdge:
    """Add a relationship edge between two nodes."""
    for edge in state.graph_edges.values():
        if (edge.source_id == source_id and edge.target_id == target_id
                and edge.relationship == relationship and edge.investigation_id == investigation_id):
            return edge

    edge = GraphEdge(
        investigation_id=investigation_id,
        source_id=source_id,
        target_id=target_id,
        relationship=relationship,
        confidence=confidence,
        properties=properties or {},
    )
    state.graph_edges[edge.id] = edge
    return edge


def build_graph_from_evidence(ev: EvidenceItem):
    """
    Build graph nodes and edges from a single evidence item's analysis + metadata.
    Called after vision analysis and metadata extraction are complete.
    """
    inv_id = ev.investigation_id
    ev_node = add_evidence_node(ev)

    # Process vision analysis entities
    if ev.analysis:
        for entity in ev.analysis.entities:
            entity_node = add_entity_node(entity, ev.id, inv_id)
            add_edge(entity_node.id, ev_node.id, "DEPICTED_IN", inv_id, entity.confidence)

            # Link entities to each other based on co-occurrence in same image
            for other_entity in ev.analysis.entities:
                if other_entity is not entity:
                    other_node = _find_node_by_label(other_entity.description, inv_id)
                    if other_node and entity_node.id != other_node.id:
                        rel = _infer_relationship(entity, other_entity)
                        if rel:
                            add_edge(entity_node.id, other_node.id, rel, inv_id,
                                     min(entity.confidence, other_entity.confidence))

    # Process GPS metadata
    parsed_meta = ev.metadata if isinstance(ev.metadata, dict) else {}
    if parsed_meta.get("gps"):
        gps_data = parsed_meta["gps"]
        if isinstance(gps_data, dict):
            gps = GPSCoordinate(**gps_data)
        else:
            gps = gps_data
        loc_node = add_location_node(gps, "", ev.id, inv_id)
        add_edge(ev_node.id, loc_node.id, "TAKEN_AT", inv_id, 1.0)

        if ev.analysis:
            for entity in ev.analysis.entities:
                entity_node = _find_node_by_label(entity.description, inv_id)
                if entity_node:
                    add_edge(entity_node.id, loc_node.id, "OBSERVED_AT", inv_id, entity.confidence)


def _infer_relationship(e1: DetectedEntity, e2: DetectedEntity) -> str | None:
    """Infer a simple relationship between two co-occurring entities."""
    types = {e1.type, e2.type}
    if EntityType.PERSON in types and EntityType.VEHICLE in types:
        return "ASSOCIATED_WITH"
    if EntityType.PERSON in types and EntityType.DEVICE in types:
        return "USES"
    if EntityType.PERSON in types and EntityType.LOCATION in types:
        return "OBSERVED_AT"
    if EntityType.VEHICLE in types and EntityType.LOCATION in types:
        return "SEEN_AT"
    if types == {EntityType.PERSON}:
        return "CO_OCCURRED_WITH"
    return None


def get_graph_summary(investigation_id: str | None = None) -> dict:
    """Return graph statistics, optionally filtered by investigation."""
    if investigation_id:
        nodes = [n for n in state.graph_nodes.values() if n.investigation_id == investigation_id]
        edges = [e for e in state.graph_edges.values() if e.investigation_id == investigation_id]
    else:
        nodes = list(state.graph_nodes.values())
        edges = list(state.graph_edges.values())

    type_counts = {}
    for n in nodes:
        t = n.type.value
        type_counts[t] = type_counts.get(t, 0) + 1

    return {
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "node_types": type_counts,
        "relationship_types": list(set(e.relationship for e in edges)),
    }
