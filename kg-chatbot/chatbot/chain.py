"""
Configura el GraphCypherQAChain que traduce preguntas en lenguaje natural
a consultas Cypher contra Neo4j y sintetiza la respuesta con Gemini.
"""

import os

from dotenv import load_dotenv
from langchain.memory import ConversationBufferWindowMemory
from langchain.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_neo4j import GraphCypherQAChain

from graph.store import get_neo4j_graph

load_dotenv(
    dotenv_path=os.path.join(os.path.dirname(__file__), '.env')
)

# Prompt que guía a Gemini para generar Cypher sobre ESTE codebase
_CYPHER_PROMPT = PromptTemplate(
    input_variables=["schema", "question"],
    template="""Eres un experto en bases de datos de grafos Neo4j. Traduce preguntas
sobre un codebase Python a consultas Cypher válidas.

El grafo representa la estructura estática del código con este esquema:

Nodos y sus propiedades clave:
- Module    : name, file_path
- Class     : name, file_path, line, docstring
- Method    : name, file_path, class_name, line, docstring, returns
- Function  : name, file_path, line, docstring, returns
- Parameter : name, parent_name, class_name, file_path, annotation, default

Relaciones:
- (Module)-[:DEFINES_CLASS]->(Class)
- (Module)-[:DEFINES_FUNCTION]->(Function)
- (Class)-[:HAS_METHOD]->(Method)
- (Class)-[:INHERITS_FROM]->(Class)
- (Method)-[:HAS_PARAMETER]->(Parameter)
- (Function)-[:HAS_PARAMETER]->(Parameter)
- (Module)-[:IMPORTS]->(Module)

Ejemplos de consultas válidas:

Búsqueda por nombre exacto:
- Métodos de una clase    : MATCH (:Class {{name:'CalloutsExtractor'}})-[:HAS_METHOD]->(m:Method) RETURN m.name, m.docstring
- Parámetros de un método : MATCH (:Method {{name:'extract_callouts'}})-[:HAS_PARAMETER]->(p:Parameter) RETURN p.name, p.annotation
- Clases de un módulo     : MATCH (:Module {{name:'callouts_extractor'}})-[:DEFINES_CLASS]->(c:Class) RETURN c.name
- Imports de un módulo    : MATCH (:Module {{name:'ingest.pipeline'}})-[:IMPORTS]->(i:Module) RETURN i.name
- Herencia                : MATCH (c:Class)-[:INHERITS_FROM]->(b:Class) RETURN c.name, b.name

Búsqueda semántica por palabra clave (usa esto cuando la pregunta es conceptual, no menciona un nombre exacto):
- Funciones relacionadas con S3   : MATCH (n) WHERE toLower(n.name) CONTAINS 's3' OR toLower(n.docstring) CONTAINS 's3' RETURN labels(n)[0] AS tipo, n.name AS nombre, n.docstring AS descripcion LIMIT 10
- Funciones que parsean algo      : MATCH (n:Function) WHERE toLower(n.name) CONTAINS 'parse' OR toLower(n.docstring) CONTAINS 'parse' RETURN n.name, n.docstring LIMIT 10
- Todo lo relacionado con XML     : MATCH (n) WHERE toLower(n.name) CONTAINS 'xml' OR toLower(n.docstring) CONTAINS 'xml' RETURN labels(n)[0] AS tipo, n.name AS nombre, n.docstring AS descripcion LIMIT 10

IMPORTANTE: Si la pregunta es conceptual (¿cómo se hace X?, ¿qué hace Y?, ¿dónde está la lógica de Z?),
extrae las palabras clave del concepto y usa CONTAINS en name y docstring para encontrar nodos relevantes.

Esquema del grafo (referencia):
{schema}

Pregunta: {question}

Genera SOLO la consulta Cypher, sin explicaciones ni markdown.
Si no puedes construir una consulta válida, responde: MATCH (n) RETURN labels(n)[0] AS tipo, n.name AS nombre LIMIT 10
""",
)

# Prompt que guía a Gemini para formular la respuesta final
_QA_PROMPT = PromptTemplate(
    input_variables=["context", "question"],
    template="""Eres un asistente experto que responde preguntas sobre un codebase
de software a partir de los datos del grafo de conocimiento.

Datos recuperados del grafo:
{context}

Pregunta: {question}

Responde de forma clara y concisa en el mismo idioma que la pregunta.
Si los datos no son suficientes para responder, dilo explícitamente.
""",
)


def build_chain(memory: ConversationBufferWindowMemory, model: str, provider: str) -> GraphCypherQAChain:
    """Construye y retorna el chain listo para recibir preguntas."""
    graph = get_neo4j_graph()
    graph.refresh_schema()  # carga el esquema actual del grafo
    llm = None
    if provider == "google":
        llm = ChatGoogleGenerativeAI(
            model=model,
            google_api_key= os.getenv("GOOGLE_API_KEY"),
            temperature=0,  # respuestas deterministas para Cypher
        )
    elif provider == "openai":
        # Configurar LLM de OpenAI si es necesario
        llm = ChatOpenAI(
            model=model,
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            temperature=0,  # respuestas deterministas para Cypher
        )
    elif provider == "anthropic":
        # Configurar LLM de Anthropic si es necesario
        llm = ChatAnthropic(
            model=model,
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            temperature=0,  # respuestas deterministas para Cypher
        )
    return GraphCypherQAChain.from_llm(
        llm=llm,
        graph=graph,
        cypher_prompt=_CYPHER_PROMPT,
        qa_prompt=_QA_PROMPT,
        allow_dangerous_requests=True,  # requerido por LangChain como medida de seguridad explícita
        verbose=True,
        return_intermediate_steps=True,  # para mostrar el Cypher en el sidebar
    )


def ask(chain: GraphCypherQAChain, question: str) -> dict:
    """
    Envía una pregunta al chain y retorna:
    {
      "answer": str,   la respuesta en lenguaje natural
      "cypher": str,   la query Cypher generada (para transparencia)
    }
    """
    result = chain.invoke({"query": question})

    # Extraer el Cypher de los pasos intermedios
    cypher = ""
    steps = result.get("intermediate_steps", [])
    if steps:
        # El primer paso contiene la query generada
        first_step = steps[0]
        if isinstance(first_step, dict):
            cypher = first_step.get("query", "")
        elif isinstance(first_step, str):
            cypher = first_step

    return {
        "answer": result.get("result", "Sin respuesta."),
        "cypher": cypher,
    }
