"""
Configures the GraphCypherQAChain that translates natural language questions
to Cypher queries against Neo4j and synthesizes the response with the chosen LLM.
"""

import os

from dotenv import load_dotenv
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_neo4j import GraphCypherQAChain

from chatbot.memory import ConversationMemory
from graph.store import get_neo4j_graph

load_dotenv(
    dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'),
    override=True,  # .env always wins over stray OS-level env vars
)

# Prompt that guides the LLM to generate Cypher for this codebase
_CYPHER_PROMPT = PromptTemplate(
    input_variables=["schema", "question"],
    template="""You are an expert in Neo4j graph databases. Translate questions
about a codebase (Python or Terraform) into valid Cypher queries.

The graph may contain two types of content:

── PYTHON CODEBASE ───────────────────────────────────────────────────────────
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

Python examples:
- Methods of a class    : MATCH (:Class {{name:'MyClass'}})-[:HAS_METHOD]->(m:Method) RETURN m.name, m.docstring
- Parameters of a method: MATCH (:Method {{name:'my_method'}})-[:HAS_PARAMETER]->(p:Parameter) RETURN p.name, p.annotation
- Imports of a module   : MATCH (:Module {{name:'ingest.pipeline'}})-[:IMPORTS]->(i:Module) RETURN i.name
- Inheritance           : MATCH (c:Class)-[:INHERITS_FROM]->(b:Class) RETURN c.name, b.name

── TERRAFORM INFRASTRUCTURE ──────────────────────────────────────────────────
Nodes and their key properties:
- TFFile     : name, file_path
- Resource   : type, name, file_path, description   (e.g. type='aws_s3_bucket', name='my_bucket')
- TFModule   : name, source, version, file_path
- Variable   : name, var_type, default, description, file_path
- Output     : name, value, description, file_path
- DataSource : type, name, file_path, description
- Provider   : type

Relationships:
- (TFFile)-[:DEFINES_RESOURCE]->(Resource)
- (TFFile)-[:CALLS_MODULE]->(TFModule)
- (TFFile)-[:DEFINES_VARIABLE]->(Variable)
- (TFFile)-[:DEFINES_OUTPUT]->(Output)
- (TFFile)-[:USES_DATA]->(DataSource)
- (TFFile)-[:USES_PROVIDER]->(Provider)

Terraform examples:
- All S3 buckets        : MATCH (r:Resource {{type:'aws_s3_bucket'}}) RETURN r.name, r.file_path
- All resources in file : MATCH (:TFFile {{file_path:'main.tf'}})-[:DEFINES_RESOURCE]->(r:Resource) RETURN r.type, r.name
- All variables         : MATCH (v:Variable) RETURN v.name, v.var_type, v.default, v.description
- All outputs           : MATCH (o:Output) RETURN o.name, o.value, o.description
- Modules used          : MATCH (f:TFFile)-[:CALLS_MODULE]->(m:TFModule) RETURN f.file_path, m.name, m.source
- Providers declared    : MATCH (f:TFFile)-[:USES_PROVIDER]->(p:Provider) RETURN f.file_path, p.type
- Data sources          : MATCH (f:TFFile)-[:USES_DATA]->(d:DataSource) RETURN d.type, d.name, f.file_path

── SEMANTIC SEARCH (for conceptual questions) ────────────────────────────────
Use CONTAINS on name/description/docstring when the question is about a concept:
- Resources related to networking: MATCH (n:Resource) WHERE toLower(n.type) CONTAINS 'vpc' OR toLower(n.type) CONTAINS 'subnet' OR toLower(n.description) CONTAINS 'network' RETURN n.type, n.name, n.file_path LIMIT 20
- Variables related to storage   : MATCH (v:Variable) WHERE toLower(v.name) CONTAINS 'storage' OR toLower(v.description) CONTAINS 'storage' RETURN v.name, v.description LIMIT 10
- Functions that parse            : MATCH (n:Function) WHERE toLower(n.name) CONTAINS 'parse' OR toLower(n.docstring) CONTAINS 'parse' RETURN n.name, n.docstring LIMIT 10

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
    template="""You are a helpful assistant with deep knowledge of the codebase.
Answer the question directly and naturally, as if you already know the codebase well.
Never start with phrases like "Based on the data", "According to the graph", or similar.
Never mention where the information comes from — just answer.
If the information is insufficient, say so briefly and suggest what to look for.

Context:
{context}

Question: {question}
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
            # Forces REST instead of gRPC — when gcloud ADC is present on the
            # machine, the gRPC transport prioritizes it over this api_key,
            # and generativelanguage.googleapis.com rejects it with
            # "ACCESS_TOKEN_TYPE_UNSUPPORTED".
            transport="rest",
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
