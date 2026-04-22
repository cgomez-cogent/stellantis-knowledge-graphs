"""
Configures the GraphCypherQAChain that translates natural language questions
to Cypher queries against Neo4j and synthesizes the response with the chosen LLM.
"""

import os

from dotenv import load_dotenv
from langchain.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_neo4j import GraphCypherQAChain

from chatbot.memory import ConversationMemory
from graph.store import get_neo4j_graph

load_dotenv(
    dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env')
)

# Prompt that guides the LLM to generate Cypher for this codebase
_CYPHER_PROMPT = PromptTemplate(
    input_variables=["schema", "question"],
    template="""You are an expert in Neo4j graph databases. Translate questions
about a Python codebase into valid Cypher queries.

The graph represents the static structure of the code with this schema:

Nodes and their key properties:
- Module    : name, file_path
- Class     : name, file_path, line, docstring
- Method    : name, file_path, class_name, line, docstring, returns
- Function  : name, file_path, line, docstring, returns
- Parameter : name, parent_name, class_name, file_path, annotation, default

Relationships:
- (Module)-[:DEFINES_CLASS]->(Class)
- (Module)-[:DEFINES_FUNCTION]->(Function)
- (Class)-[:HAS_METHOD]->(Method)
- (Class)-[:INHERITS_FROM]->(Class)
- (Method)-[:HAS_PARAMETER]->(Parameter)
- (Function)-[:HAS_PARAMETER]->(Parameter)
- (Module)-[:IMPORTS]->(Module)

Examples of valid queries:

Exact name search:
- Methods of a class    : MATCH (:Class {{name:'CalloutsExtractor'}})-[:HAS_METHOD]->(m:Method) RETURN m.name, m.docstring
- Parameters of a method: MATCH (:Method {{name:'extract_callouts'}})-[:HAS_PARAMETER]->(p:Parameter) RETURN p.name, p.annotation
- Classes of a module   : MATCH (:Module {{name:'callouts_extractor'}})-[:DEFINES_CLASS]->(c:Class) RETURN c.name
- Imports of a module   : MATCH (:Module {{name:'ingest.pipeline'}})-[:IMPORTS]->(i:Module) RETURN i.name
- Inheritance           : MATCH (c:Class)-[:INHERITS_FROM]->(b:Class) RETURN c.name, b.name

Semantic keyword search (use this when the question is conceptual, not an exact name):
- Functions related to S3  : MATCH (n) WHERE toLower(n.name) CONTAINS 's3' OR toLower(n.docstring) CONTAINS 's3' RETURN labels(n)[0] AS type, n.name AS name, n.docstring AS description LIMIT 10
- Functions that parse      : MATCH (n:Function) WHERE toLower(n.name) CONTAINS 'parse' OR toLower(n.docstring) CONTAINS 'parse' RETURN n.name, n.docstring LIMIT 10
- Everything related to XML : MATCH (n) WHERE toLower(n.name) CONTAINS 'xml' OR toLower(n.docstring) CONTAINS 'xml' RETURN labels(n)[0] AS type, n.name AS name, n.docstring AS description LIMIT 10

IMPORTANT: If the question is conceptual (How is X done? What does Y do? Where is the logic of Z?),
extract the keywords from the concept and use CONTAINS on name and docstring to find relevant nodes.

Graph schema (reference):
{schema}

Question: {question}

Generate ONLY the Cypher query, without explanations or markdown.
If you cannot build a valid query, respond with: MATCH (n) RETURN labels(n)[0] AS type, n.name AS name LIMIT 10
""",
)

# Prompt that guides the LLM to formulate the final answer
_QA_PROMPT = PromptTemplate(
    input_variables=["context", "question"],
    template="""You are an expert assistant that answers questions about a software
codebase based on knowledge graph data.

Data retrieved from the graph:
{context}

Question: {question}

Answer clearly and concisely in English.
If the data is insufficient to answer, state it explicitly.
""",
)


def build_chain(model: str, provider: str) -> GraphCypherQAChain:
    """Builds and returns the chain ready to receive questions."""
    graph = get_neo4j_graph()
    graph.refresh_schema()  # loads the current graph schema
    llm = None
    if provider == "google":
        llm = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            temperature=0,  # deterministic responses for Cypher
        )
    elif provider == "openai":
        # Configure OpenAI LLM
        llm = ChatOpenAI(
            model=model,
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            temperature=0,  # deterministic responses for Cypher
        )
    elif provider == "anthropic":
        # Configure Anthropic LLM
        llm = ChatAnthropic(
            model=model,
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            temperature=0,  # deterministic responses for Cypher
        )
    return GraphCypherQAChain.from_llm(
        llm=llm,
        graph=graph,
        cypher_prompt=_CYPHER_PROMPT,
        qa_prompt=_QA_PROMPT,
        allow_dangerous_requests=True,  # required by LangChain as an explicit safety measure
        verbose=True,
        return_intermediate_steps=True,  # to display the Cypher in the sidebar
    )


def ask(chain: GraphCypherQAChain, question: str, memory: ConversationMemory | None = None) -> dict:
    """
    Sends a question to the chain and returns:
    {
      "answer": str,   the natural language answer
      "cypher": str,   the generated Cypher query (for transparency)
    }

    If memory is provided, the conversation history is prepended to the question
    so the LLM can resolve references like "that class" or "its methods".
    After a successful response the turn is stored in memory.
    """
    enriched_question = question
    if memory and not memory.is_empty:
        history = memory.as_context_string()
        enriched_question = (
            f"Conversation history:\n{history}\n\nCurrent question: {question}"
        )

    result = chain.invoke({"query": enriched_question})

    # Extract the Cypher from intermediate steps
    cypher = ""
    steps = result.get("intermediate_steps", [])
    if steps:
        first_step = steps[0]
        if isinstance(first_step, dict):
            cypher = first_step.get("query", "")
        elif isinstance(first_step, str):
            cypher = first_step

    answer = result.get("result", "No answer.")

    if memory is not None:
        memory.add_turn(human=question, ai=answer)

    return {
        "answer": answer,
        "cypher": cypher,
    }
