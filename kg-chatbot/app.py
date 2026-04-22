"""
Streamlit UI — Knowledge Graph Chatbot

Run with:
    streamlit run app.py
"""

import asyncio

import streamlit as st

from chatbot.chain import ask, build_chain
from chatbot.memory import get_memory
from ingest.pipeline import run_ingestion

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

LLM_OPTIONS = {
    "google": ["gemini-3.1-flash-lite-preview", "gemini-2.5-flash", "gemini-2.5-flash-lite"],
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

    # Re-ingestion
    st.subheader("Re-index codebase")
    folder_path = st.text_input(
        "Codebase path",
        placeholder="/path/to/project",
        help="Absolute or relative path to the codebase you want to index.",
    )
    if st.button("▶ Start ingestion", disabled=not folder_path):
        with st.spinner(f"Indexing {folder_path}..."):
            try:
                asyncio.run(run_ingestion(folder_path))
                st.success("Ingestion completed. Reload the page to use the updated graph.")
                # Force chain reload to reflect the new schema
                st.session_state.chain = build_chain(model=model, provider=provider)
            except Exception as exc:
                st.error(f"Error during ingestion: {exc}")

    st.divider()
    st.caption("Neo4j browser → http://localhost:7474")

# ── Main chat area ───────────────────────────────────────────────────────────

st.title("💬 Chat with your codebase")

# Show connection error if it occurred during initialization
if st.session_state.chain_error:
    st.error(
        f"Could not connect to Neo4j:\n\n{st.session_state.chain_error}\n\n"
        "Verify that Docker is running and your `.env` is correct."
    )

# Render message history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# User input
if prompt := st.chat_input("Ask about your codebase..."):
    # Show user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Generate response
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
