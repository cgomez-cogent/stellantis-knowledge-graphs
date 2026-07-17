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
- Method    : name, file_path, class_name, line, docstring, returns, string_literals
- Function  : name, file_path, line, docstring, returns, string_literals
- Parameter : name, parent_name, class_name, file_path, annotation, default

`string_literals` is a LIST of the string constants/magic values used inside
the function/method body (e.g. business codes, keys, flags like "TRM" or
"ACTIVE_IND"). Use it to answer questions about internal logic/behavior that
isn't described in the docstring — e.g. "where do we use code X",
"what handles the TRM field". Search it with
`any(lit IN n.string_literals WHERE toLower(lit) CONTAINS 'x')`.

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

── SEMANTIC SEARCH (for conceptual / non-technical questions) ────────────────
Most real users do NOT know exact class/function/variable names — they ask about
a business concept in plain language (e.g. "how do we get the color of a part?",
"where do we validate a VIN?", "what handles pricing?"). For these questions:

- NEVER use exact equality (`{{name:'X'}}`) unless the question literally quotes
  an identifier. Default to case-insensitive `CONTAINS` on every text property
  that could hold the concept: name, docstring, description, annotation,
  class_name, returns, default.
- Think of 2-4 related keywords/synonyms for the SPECIFIC concept (e.g. "color" →
  'color', 'colour', 'paint', 'hue') and OR them together.
- Do NOT add generic domain nouns as extra OR keywords just because they appear
  in the question (e.g. "part"/"parts", "record", "item", "data", "file"). In a
  codebase about a specific domain, these words match a huge fraction of all
  nodes — OR-ing them in adds noise that can crowd the real, specific matches
  out of the LIMIT entirely. Only search for the word that actually narrows
  down the result (e.g. for "the color of the parts", search 'color'/'colour',
  NOT 'part').
- Search across ALL node labels that could plausibly hold the concept in one
  query, instead of guessing a single label. Use `any(lbl IN labels(n) WHERE
  lbl IN [...])` for this — NEVER write `n:Class OR n:Method OR ...` (repeated
  colon-label checks on the same variable are a common source of malformed
  Cypher). NEVER wrap label names in backticks unless the label itself
  literally contains a space or special character.
- If you do need to combine more than one concept (e.g. two genuinely distinct
  keywords that both matter), rank instead of just OR-and-LIMIT: compute how
  many keyword groups each node matches with a `WITH n, (CASE WHEN ... THEN 1
  ELSE 0 END) + (CASE WHEN ... THEN 1 ELSE 0 END) AS score` and `ORDER BY score
  DESC` before the `LIMIT`, so the most relevant nodes surface first instead of
  being pushed out by whichever keyword happens to be more common.
- Always LIMIT results (10-20) and return `labels(n)[0] AS type` plus the
  matched name/docstring so the answer can explain what was found and where.
- If the question mentions a short code/field/flag (e.g. "TRM", "ACTIVE_IND")
  that isn't a normal English word, it's likely a business/magic value used
  INSIDE a function's logic, not its name or docstring — search
  `string_literals` on Function/Method too, not just name/docstring.

Examples:
- "How do we get the color of the parts?" (the specific/narrowing term is
  "color" — "parts" is generic domain noise here, do NOT OR it in):
  MATCH (n) WHERE any(lbl IN labels(n) WHERE lbl IN ['Class','Method','Function','Parameter'])
  AND (toLower(n.name) CONTAINS 'color' OR toLower(n.name) CONTAINS 'colour'
       OR toLower(n.docstring) CONTAINS 'color' OR toLower(n.docstring) CONTAINS 'colour')
  RETURN labels(n)[0] AS type, n.name, n.file_path, n.docstring LIMIT 20
- "How do we work with TRM?" (a code, not an English word — check string_literals):
  MATCH (n) WHERE any(lbl IN labels(n) WHERE lbl IN ['Function','Method'])
  AND (toLower(n.name) CONTAINS 'trm' OR toLower(n.docstring) CONTAINS 'trm'
       OR any(lit IN n.string_literals WHERE toLower(lit) CONTAINS 'trm'))
  RETURN labels(n)[0] AS type, n.name, n.file_path, n.docstring, n.string_literals LIMIT 20
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
    template="""You are a helpful assistant with deep knowledge of a specific codebase,
whose only source of truth is the Context below (retrieved from a Neo4j knowledge graph).

Strict rules:
- Answer using ONLY information present in Context. Never use outside/general knowledge,
  never write new code, and never solve generic programming, math, or trivia questions —
  even if you know the answer. Your job is to report what is in the graph, not to be a
  general-purpose assistant.
- If Context is empty or does not contain enough information to answer confidently, say
  clearly that you could not find that information in the codebase graph. Do not guess or
  make up an answer. Optionally suggest a close, related question the user might have meant
  (based only on names/concepts that DO appear in Context, if any), and ask them to confirm
  or rephrase.
- If the question is not about the indexed codebase/infrastructure at all (e.g. asking you
  to write a function, do unrelated general knowledge, etc.), say that you can only answer
  questions about the code and infrastructure indexed in the graph.
- When you do answer from Context, answer directly and naturally, as if you already know the
  codebase well. Never start with phrases like "Based on the data", "According to the graph",
  or similar, and never mention where the information comes from.
- Assume the person asking is NOT a programmer and may not know class/function/file names.
  Explain in plain, everyday language what the code does and where, instead of just dumping
  raw property names. Briefly translate technical terms if you use them (e.g. "the
  `get_part_color` function, which looks up a part's color").
- NEVER expand, define, or guess the meaning of an acronym/abbreviation/code (e.g. "EPC",
  "TRM", "ESPCLR") unless Context itself literally states what it stands for. Codebases
  routinely reuse acronyms for company- or project-specific things that do NOT match their
  common industry meaning — inventing a plausible-sounding expansion (even a well-known one
  like "Electronic Parts Catalog" for "EPC") is a hallucination. If Context doesn't say what
  it means, just use the acronym as-is and, if useful, say its meaning isn't documented here.

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

    # Extract the Cypher and the raw query results from intermediate steps
    cypher = ""
    context = None
    steps = result.get("intermediate_steps", [])
    if steps:
        first_step = steps[0]
        if isinstance(first_step, dict):
            cypher = first_step.get("query", "")
        elif isinstance(first_step, str):
            cypher = first_step
    if len(steps) > 1 and isinstance(steps[1], dict):
        context = steps[1].get("context")

    # Don't trust the QA LLM's answer if the Cypher query returned nothing —
    # it tends to fabricate a plausible-sounding answer instead of admitting
    # it found no matching nodes. Short-circuit with a fixed message so this
    # behavior doesn't depend on the LLM following the prompt's instructions.
    if not cypher or context == []:
        answer = (
            "I couldn't find any matching information in the codebase graph "
            "for that question. Could you rephrase it, or let me know if you "
            "meant something similar (e.g. a different class, function, or "
            "resource name)?"
        )
    else:
        answer = result.get("result", "No answer.")

    if memory is not None:
        memory.add_turn(human=question, ai=answer)

    return {
        "answer": answer,
        "cypher": cypher,
    }
