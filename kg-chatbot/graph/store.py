"""
Central factory for Neo4j connections.

Exports:
  get_neo4j_graph()  → Neo4jGraph  (for LangChain GraphCypherQAChain)
  get_neo4j_driver() → Driver      (for direct ingestion via graph_writer)

Migration to Amazon Neptune
───────────────────────────
To point to Neptune instead of local Neo4j, change these variables in .env:

  NEO4J_URI      → bolt+s://<your-cluster>.neptune.amazonaws.com:8182
  NEO4J_USER     → (IAM user, or empty if using IAM auth)
  NEO4J_PASSWORD → (IAM token, or empty)
"""

import os

from dotenv import load_dotenv
from langchain_neo4j import Neo4jGraph
from neo4j import GraphDatabase, Driver

load_dotenv(override=True)  # .env always wins over stray OS-level env vars

_NEO4J_URI = os.getenv("NEO4J_URI")
_NEO4J_USER = os.getenv("NEO4J_USER")
_NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
_NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")


def get_neo4j_graph() -> Neo4jGraph:
    """Returns a ready-to-use Neo4jGraph for GraphCypherQAChain."""
    return Neo4jGraph(
        url=_NEO4J_URI,
        username=_NEO4J_USER,
        password=_NEO4J_PASSWORD,
        database=_NEO4J_DATABASE,
    )


def get_neo4j_driver() -> Driver:
    """Returns the native Neo4j driver for write operations during ingestion."""
    return GraphDatabase.driver(
        _NEO4J_URI,
        auth=(_NEO4J_USER, _NEO4J_PASSWORD),
    )
