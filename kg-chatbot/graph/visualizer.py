"""
Graphistry visualization module.

Fetches nodes and edges from Neo4j and builds interactive Graphistry plots.
Requires GRAPHISTRY_USERNAME and GRAPHISTRY_PASSWORD in .env
(free account at https://hub.graphistry.com).
"""

import os
from typing import Optional

import pandas as pd

from graph.store import get_neo4j_driver

NODE_COLORS = {
    # Python
    "Module":     "#4A90E2",
    "Class":      "#7B68EE",
    "Method":     "#50C878",
    "Function":   "#FF6B6B",
    "Parameter":  "#FFB347",
    # Terraform
    "TFFile":     "#E8A838",
    "Resource":   "#E84393",
    "TFModule":   "#38C8E8",
    "Variable":   "#A8E838",
    "Output":     "#E85C38",
    "DataSource": "#9B38E8",
    "Provider":   "#38E8A0",
}
DEFAULT_COLOR = "#AAAAAA"

NODE_LABELS = [
    "Module", "Class", "Method", "Function", "Parameter",
    "TFFile", "Resource", "TFModule", "Variable", "Output", "DataSource", "Provider",
]
RELATIONSHIP_TYPES = [
    "DEFINES_CLASS", "DEFINES_FUNCTION", "HAS_METHOD", "INHERITS_FROM", "HAS_PARAMETER", "IMPORTS",
    "DEFINES_RESOURCE", "CALLS_MODULE", "DEFINES_VARIABLE", "DEFINES_OUTPUT", "USES_DATA", "USES_PROVIDER",
]


def register_graphistry() -> None:
    """Register with Graphistry Hub. Call once per session."""
    import graphistry  # imported here so the rest of the app works without it

    key_id = os.getenv("GRAPHISTRY_KEY_ID", "")
    key_secret = os.getenv("GRAPHISTRY_KEY_SECRET", "")

    if not key_id or not key_secret:
        raise EnvironmentError(
            "Set GRAPHISTRY_KEY_ID and GRAPHISTRY_KEY_SECRET in your .env file.\n"
            "Find your personal keys at https://hub.graphistry.com → API Keys"
        )

    graphistry.register(
        api=3,
        personal_key_id=key_id,
        personal_key_secret=key_secret,
        protocol="https",
        server="hub.graphistry.com",
    )


def fetch_graph_data(
    node_label: Optional[str] = None,
    rel_type: Optional[str] = None,
    limit: int = 500,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns (nodes_df, edges_df) as pandas DataFrames.

    node_label: filter to nodes of this label (None = all)
    rel_type:   filter to edges of this relationship type (None = all)
    limit:      max nodes fetched
    """
    node_filter = f":{node_label}" if node_label else ""
    rel_filter = f":{rel_type}" if rel_type else ""

    # Single query returning nodes + relationships together so elementIds align.
    connected_query = f"""
        MATCH (a{node_filter})-[r{rel_filter}]->(b)
        RETURN a, r, b
        LIMIT {limit}
    """
    isolated_query = f"""
        MATCH (n{node_filter})
        WHERE NOT (n{node_filter})-[{rel_filter if rel_filter else ""}]->()
          AND NOT ()-[{rel_filter if rel_filter else ""}]->(n{node_filter})
        RETURN n
        LIMIT {limit}
    """

    nodes_map: dict = {}
    edges_map: dict = {}

    driver = get_neo4j_driver()
    with driver.session() as session:
        for record in session.run(connected_query):
            for value in record.values():
                _extract_element(value, nodes_map, edges_map)

        # Include isolated nodes (no relationships matching the filter)
        for record in session.run(isolated_query):
            for value in record.values():
                _extract_element(value, nodes_map, edges_map)

    driver.close()

    nodes_df = pd.DataFrame(list(nodes_map.values())) if nodes_map else pd.DataFrame()
    edges_df = pd.DataFrame(list(edges_map.values())) if edges_map else pd.DataFrame()
    return nodes_df, edges_df


def _to_viz_cypher(cypher: str) -> str:
    """
    Rewrites a property-returning Cypher into one that returns full nodes/rels.

    MATCH (m:Method) RETURN m.name, m.docstring LIMIT 10
    → MATCH (m:Method) RETURN m LIMIT 10
    """
    import re

    parts = re.split(r"\bRETURN\b", cypher, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) < 2:
        return cypher

    match_part, return_part = parts

    limit_match = re.search(r"\bLIMIT\s+\d+", return_part, flags=re.IGNORECASE)
    limit_clause = (" " + limit_match.group(0)) if limit_match else ""

    # variables declared in the MATCH part: (var:...) or (var {...)  or (var)
    node_vars = re.findall(r"\(([a-zA-Z_]\w*)(?:\s*[:{)])", match_part)
    # relationship variables: [var:...] or [var]
    rel_vars = re.findall(r"\[([a-zA-Z_]\w*)(?:\s*[:{]])", match_part)

    all_vars = list(dict.fromkeys(node_vars + rel_vars))
    if not all_vars:
        return cypher

    return match_part + "RETURN " + ", ".join(all_vars) + limit_clause


def fetch_cypher_graph(cypher: str, limit: int = 300) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Run an arbitrary Cypher query that returns nodes/relationships
    and convert the result to (nodes_df, edges_df).
    Only records containing node or relationship objects are processed.
    """
    cypher = _to_viz_cypher(cypher)
    driver = get_neo4j_driver()
    nodes_map: dict[int, dict] = {}
    edges_map: dict[int, dict] = {}

    with driver.session() as session:
        result = session.run(cypher)
        for record in result:
            for value in record.values():
                _extract_element(value, nodes_map, edges_map)
                if len(nodes_map) >= limit:
                    break

        # When the query returns only nodes, fetch relationships between them
        # so Graphistry can run its layout engine and display something useful.
        if nodes_map and not edges_map:
            node_ids = list(nodes_map.keys())
            rel_result = session.run(
                "MATCH (a)-[r]->(b) WHERE elementId(a) IN $ids AND elementId(b) IN $ids RETURN r LIMIT 500",
                ids=node_ids,
            )
            for record in rel_result:
                for value in record.values():
                    _extract_element(value, nodes_map, edges_map)

    driver.close()

    nodes_df = pd.DataFrame(list(nodes_map.values())) if nodes_map else pd.DataFrame()
    edges_df = pd.DataFrame(list(edges_map.values())) if edges_map else pd.DataFrame()
    return nodes_df, edges_df


def _extract_element(value, nodes_map, edges_map) -> None:
    """Recursively extract graph elements from a Cypher record value."""
    from neo4j.graph import Node, Relationship  # type: ignore

    if isinstance(value, Node):
        nid = value.element_id
        if nid not in nodes_map:
            props = dict(value)
            # Build a human-readable label: prefer name, then type, then file_path
            display_name = (
                props.get("name")
                or props.get("type")
                or props.get("file_path")
                or str(nid)
            )
            nodes_map[nid] = {
                "id": nid,
                "label": list(value.labels)[0] if value.labels else "Unknown",
                "display_name": display_name,
                **props,
            }
    elif isinstance(value, Relationship):
        eid = value.element_id
        if eid not in edges_map:
            edges_map[eid] = {
                "id": eid,
                "src": value.start_node.element_id,
                "dst": value.end_node.element_id,
                "rel_type": value.type,
            }
            _extract_element(value.start_node, nodes_map, edges_map)
            _extract_element(value.end_node, nodes_map, edges_map)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _extract_element(item, nodes_map, edges_map)


def _hex_to_int(hex_color: str) -> int:
    """Convert #RRGGBB to Graphistry's ARGB integer format."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (255 << 24) | (r << 16) | (g << 8) | b


def build_graphistry_url(nodes_df: pd.DataFrame, edges_df: pd.DataFrame) -> str:
    """
    Build a Graphistry interactive plot and return the shareable URL.
    Requires register_graphistry() to have been called first.
    """
    import graphistry  # noqa: PLC0415

    if nodes_df.empty:
        raise ValueError("No graph data to visualize.")

    nodes_df = nodes_df.copy()
    nodes_df["color"] = (
        nodes_df["label"]
        .map(NODE_COLORS)
        .fillna(DEFAULT_COLOR)
        .apply(_hex_to_int)
    )

    if edges_df.empty:
        edges_df = pd.DataFrame({"src": pd.Series(dtype=object), "dst": pd.Series(dtype=object), "rel_type": pd.Series(dtype=str)})

    g = (
        graphistry
        .edges(edges_df, "src", "dst")
        .nodes(nodes_df, "id")
        .bind(point_title="display_name", edge_label="rel_type", point_color="color")
    )

    return g.plot(render=False)
