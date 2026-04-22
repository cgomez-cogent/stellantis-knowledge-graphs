"""
Fábrica central de conexiones Neo4j.

Exporta:
  get_neo4j_graph()  → Neo4jGraph  (para LangChain GraphCypherQAChain)
  get_neo4j_driver() → Driver      (para ingesta directa via graph_writer)

Migración a Amazon Neptune
──────────────────────────
Para apuntar a Neptune en lugar de Neo4j local, cambia estas variables en .env:

  NEO4J_URI      → bolt+s://<tu-cluster>.neptune.amazonaws.com:8182
  NEO4J_USER     → (usuario IAM, o vacío si usas autenticación IAM)
  NEO4J_PASSWORD → (token IAM, o vacío)
"""

import os

from dotenv import load_dotenv
from langchain_neo4j import Neo4jGraph
from neo4j import GraphDatabase, Driver

load_dotenv()

_NEO4J_URI = os.getenv("NEO4J_URI")
_NEO4J_USER = os.getenv("NEO4J_USER")
_NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
_NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")


def get_neo4j_graph() -> Neo4jGraph:
    """Retorna un Neo4jGraph listo para GraphCypherQAChain."""
    return Neo4jGraph(
        url=_NEO4J_URI,
        username=_NEO4J_USER,
        password=_NEO4J_PASSWORD,
        database=_NEO4J_DATABASE,
    )


def get_neo4j_driver() -> Driver:
    """Retorna el driver nativo de Neo4j para operaciones de escritura en ingesta."""
    return GraphDatabase.driver(
        _NEO4J_URI,
        auth=(_NEO4J_USER, _NEO4J_PASSWORD),
    )
