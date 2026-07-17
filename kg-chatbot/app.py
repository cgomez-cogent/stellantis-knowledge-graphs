"""
Streamlit UI — Knowledge Graph Chatbot

Run with:
    streamlit run app.py
"""

import os

import streamlit as st

# On Streamlit Community Cloud, config comes from the app's "Secrets" panel
# (st.secrets), not from a .env file. Mirror it into os.environ *before*
# importing any project module, since graph/store.py reads Neo4j settings
# at import time. Locally, with no secrets.toml, st.secrets raises — fall
# back to the .env file loaded by the project modules themselves.
def _flatten_secrets(mapping, out):
    for key, value in mapping.items():
        # Secrets pasted under a [section] header come back as a nested
        # mapping — flatten one level so NEO4J_URI etc. still land as
        # top-level env vars regardless of how the TOML was structured.
        if hasattr(value, "items"):
            _flatten_secrets(value, out)
        else:
            out.setdefault(key, str(value))


try:
    _env_from_secrets = {}
    _flatten_secrets(st.secrets, _env_from_secrets)
    os.environ.update(_env_from_secrets)
except FileNotFoundError:
    pass

from chatbot.chain import ask, build_chain
from chatbot.memory import get_memory
from graph.visualizer import (
    NODE_COLORS,
    NODE_LABELS,
    RELATIONSHIP_TYPES,
    build_graphistry_url,
    fetch_cypher_graph,
    fetch_graph_data,
    register_graphistry,
)

st.set_page_config(
    page_title="KG Chatbot",
    page_icon="🔍",
    layout="wide",
)

# ── Session state initialization ────────────────────────────────────────────

if "messages" not in st.session_state:
    st.session_state.messages = []

if "memory" not in st.session_state:
    st.session_state.memory = get_memory()

if "chain" not in st.session_state:
    st.session_state.chain = None
    st.session_state.chain_error = None

if "last_cypher" not in st.session_state:
    st.session_state.last_cypher = ""

if "active_provider" not in st.session_state:
    st.session_state.active_provider = None

if "active_model" not in st.session_state:
    st.session_state.active_model = None

if "graphistry_registered" not in st.session_state:
    st.session_state.graphistry_registered = False

if "graphistry_error" not in st.session_state:
    st.session_state.graphistry_error = None

if "graph_url" not in st.session_state:
    st.session_state.graph_url = None

LLM_OPTIONS = {
    "google": ["gemini-3.1-flash-lite-preview", "gemini-flash-latest", "gemini-2.0-flash"],
    "openai": ["gpt-4", "gpt-4o", "gpt-3.5-turbo"],
    "anthropic": ["claude-3-opus", "claude-3-sonnet"]
}
# ── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🔍 KG Chatbot")
    st.caption("Query your codebase in natural language")

    st.divider()

    st.subheader("LLM Configuration")

    # Select provider
    provider = st.selectbox(
        "LLM Provider",
        options=list(LLM_OPTIONS.keys()),
        help="Select the model provider.",
        key="llm_provider",
    )

    # Dynamic model selection
    model = st.selectbox(
        "LLM Model",
        options=LLM_OPTIONS[provider],
        help="Select the model based on the chosen provider.",
        key="llm_model",
    )

    # Build or rebuild the chain if provider/model changed
    if provider != st.session_state.active_provider or model != st.session_state.active_model:
        with st.spinner(f"Loading {provider} / {model}..."):
            try:
                st.session_state.chain = build_chain(model=model, provider=provider)
                st.session_state.chain_error = None
                st.session_state.active_provider = provider
                st.session_state.active_model = model
            except Exception as exc:
                st.session_state.chain = None
                st.session_state.chain_error = str(exc)
                st.session_state.active_provider = provider
                st.session_state.active_model = model

    # Last generated Cypher query
    st.subheader("Generated Cypher")
    if st.session_state.last_cypher:
        st.code(st.session_state.last_cypher, language="cypher")
    else:
        st.caption("The Cypher query will appear here after your first question.")

    st.divider()
    st.caption(
        "Re-indexing was moved out of the UI for security — any allowed "
        "viewer could otherwise wipe the shared graph. Run "
        "`python -m ingest.pipeline /path/to/project` locally instead."
    )

    st.divider()
    st.caption("Neo4j browser → http://localhost:7474")

# ── Main area — tabs ─────────────────────────────────────────────────────────

tab_chat, tab_graph = st.tabs(["💬 Chat", "🔗 Graph Visualization"])

# ── Tab 1: Chat ───────────────────────────────────────────────────────────────

with tab_chat:
    st.title("💬 Chat with your codebase")

    if st.session_state.chain_error:
        st.error(
            f"Could not connect to Neo4j:\n\n{st.session_state.chain_error}\n\n"
            "Verify that Docker is running and your `.env` is correct."
        )

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Ask about your codebase..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            if st.session_state.chain is None:
                answer = "No Neo4j connection. Check the configuration in the sidebar."
                st.markdown(answer)
            else:
                with st.spinner("Querying the graph..."):
                    try:
                        result = ask(st.session_state.chain, prompt, memory=st.session_state.memory)
                        answer = result["answer"]
                        st.session_state.last_cypher = result["cypher"]
                        st.session_state.messages.append({"role": "assistant", "content": answer})
                        st.rerun()
                    except Exception as exc:
                        answer = f"Error querying the graph: {exc}"
                        st.error(answer)
                        st.session_state.messages.append({"role": "assistant", "content": answer})

# ── Tab 2: Graph Visualization ────────────────────────────────────────────────

with tab_graph:
    st.title("🔗 Graph Visualization")
    st.caption("Interactive graph powered by [Graphistry](https://hub.graphistry.com)")

    # ── Graphistry credentials check ─────────────────────────────────────────
    if not st.session_state.graphistry_registered:
        with st.spinner("Connecting to Graphistry Hub..."):
            try:
                register_graphistry()
                st.session_state.graphistry_registered = True
                st.session_state.graphistry_error = None
            except EnvironmentError as exc:
                st.session_state.graphistry_error = str(exc)
            except Exception as exc:
                st.session_state.graphistry_error = f"Graphistry connection error: {exc}"

    if st.session_state.graphistry_error:
        st.error(st.session_state.graphistry_error)
        st.info(
            "Add these variables to your `.env` file:\n\n"
            "```\nGRAPHISTRY_KEY_ID=your_personal_key_id\n"
            "GRAPHISTRY_KEY_SECRET=your_personal_key_secret\n```\n\n"
            "Find your keys at https://hub.graphistry.com → API Keys"
        )
        st.stop()

    # ── Legend ────────────────────────────────────────────────────────────────
    with st.expander("Node color legend", expanded=False):
        cols = st.columns(len(NODE_COLORS))
        for col, (label, color) in zip(cols, NODE_COLORS.items()):
            col.markdown(
                f'<span style="display:inline-block;width:14px;height:14px;'
                f'border-radius:50%;background:{color};margin-right:6px"></span>**{label}**',
                unsafe_allow_html=True,
            )

    # ── Visualization mode ────────────────────────────────────────────────────
    viz_mode = st.radio(
        "Visualization source",
        ["Full graph", "Last chat query"],
        horizontal=True,
    )

    st.divider()

    if viz_mode == "Full graph":
        col_left, col_right = st.columns([1, 1])
        with col_left:
            node_filter = st.selectbox(
                "Filter by node type",
                ["All"] + NODE_LABELS,
                help="Show only nodes of this type (and their relationships).",
            )
        with col_right:
            rel_filter = st.selectbox(
                "Filter by relationship",
                ["All"] + RELATIONSHIP_TYPES,
            )
        node_limit = st.slider("Max nodes", min_value=50, max_value=1000, value=300, step=50)

        if st.button("🔄 Visualize full graph", type="primary"):
            with st.spinner("Fetching data from Neo4j and rendering with Graphistry..."):
                try:
                    n_label = None if node_filter == "All" else node_filter
                    r_type = None if rel_filter == "All" else rel_filter
                    nodes_df, edges_df = fetch_graph_data(
                        node_label=n_label, rel_type=r_type, limit=node_limit
                    )
                    if nodes_df.empty:
                        st.warning("No nodes found with the selected filters.")
                    else:
                        st.session_state.graph_url = build_graphistry_url(nodes_df, edges_df)
                        st.caption(
                            f"Loaded **{len(nodes_df)}** nodes and **{len(edges_df)}** edges."
                        )
                except Exception as exc:
                    st.error(f"Visualization error: {exc}")

    else:  # Last chat query
        if not st.session_state.last_cypher:
            st.info("Ask a question in the Chat tab first — the last Cypher query will be visualized here.")
        else:
            st.code(st.session_state.last_cypher, language="cypher")
            if st.button("🔄 Visualize last query", type="primary"):
                with st.spinner("Running query and rendering with Graphistry..."):
                    try:
                        nodes_df, edges_df = fetch_cypher_graph(st.session_state.last_cypher)
                        if nodes_df.empty:
                            st.warning(
                                "The last query returned no graph elements (nodes/relationships). "
                                "Try a query that returns nodes, e.g. `MATCH (n) RETURN n LIMIT 50`."
                            )
                        else:
                            st.session_state.graph_url = build_graphistry_url(nodes_df, edges_df)
                            st.caption(
                                f"Loaded **{len(nodes_df)}** nodes and **{len(edges_df)}** edges."
                            )
                    except Exception as exc:
                        st.error(f"Visualization error: {exc}")

    # ── Render iframe ─────────────────────────────────────────────────────────
    if st.session_state.graph_url:
        st.markdown("---")
        st.caption(f"[Open in a new tab]({st.session_state.graph_url}) if it doesn't render below.")
        st.iframe(st.session_state.graph_url, height=620)
