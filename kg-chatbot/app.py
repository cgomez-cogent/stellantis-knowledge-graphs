"""
Streamlit UI — Knowledge Graph Chatbot

Ejecutar con:
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

# ── Inicialización del estado de sesión ─────────────────────────────────────

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
    "google": ["gemini-pro", "gemini-1.5-pro"],
    "openai": ["gpt-4", "gpt-4o", "gpt-3.5-turbo"],
    "anthropic": ["claude-3-opus", "claude-3-sonnet"]
}
# ── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🔍 KG Chatbot")
    st.caption("Consulta tu codebase en lenguaje natural")

    st.divider()

    st.subheader("Configuración del LLM")
    # Definir providers y modelos

    # Select provider
    provider = st.selectbox(
        "Proveedor de LLM",
        options=list(LLM_OPTIONS.keys()),
        help="Selecciona el proveedor del modelo.",
        key="llm_provider",
    )

    # Select model dinámico
    model = st.selectbox(
        "Modelo de LLM",
        options=LLM_OPTIONS[provider],
        help="Selecciona el modelo según el proveedor elegido.",
        key="llm_model",
    )

    # Construir o reconstruir el chain si cambiaron provider/model
    if provider != st.session_state.active_provider or model != st.session_state.active_model:
        with st.spinner(f"Cargando {provider} / {model}..."):
            try:
                st.session_state.chain = build_chain(st.session_state.memory, model=model, provider=provider)
                st.session_state.chain_error = None
                st.session_state.active_provider = provider
                st.session_state.active_model = model
            except Exception as exc:
                st.session_state.chain = None
                st.session_state.chain_error = str(exc)
                st.session_state.active_provider = provider
                st.session_state.active_model = model

    # Última query Cypher generada
    st.subheader("Cypher generado")
    if st.session_state.last_cypher:
        st.code(st.session_state.last_cypher, language="cypher")
    else:
        st.caption("La query Cypher aparecerá aquí después de tu primera pregunta.")

    st.divider()

    # Re-ingesta
    st.subheader("Re-indexar codebase")
    folder_path = st.text_input(
        "Ruta del codebase",
        placeholder="/ruta/al/proyecto",
        help="Ruta absoluta o relativa al codebase que quieres indexar.",
    )
    if st.button("▶ Iniciar ingesta", disabled=not folder_path):
        with st.spinner(f"Indexando {folder_path}..."):
            try:
                asyncio.run(run_ingestion(folder_path))
                st.success("Ingesta completada. Recarga la página para usar el grafo actualizado.")
                # Forzar recarga del chain para reflejar el nuevo esquema
                st.session_state.chain = build_chain(st.session_state.memory, model=model, provider=provider)
            except Exception as exc:
                st.error(f"Error durante la ingesta: {exc}")

    st.divider()
    st.caption("Neo4j browser → http://localhost:7474")

# ── Área principal de chat ───────────────────────────────────────────────────

st.title("💬 Chat con tu codebase")

# Mostrar error de conexión si ocurrió al inicializar
if st.session_state.chain_error:
    st.error(
        f"No se pudo conectar con Neo4j:\n\n{st.session_state.chain_error}\n\n"
        "Verifica que Docker esté corriendo y que tu `.env` sea correcto."
    )

# Renderizar historial de mensajes
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Input del usuario
if prompt := st.chat_input("Pregunta sobre tu codebase..."):
    # Mostrar mensaje del usuario
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Generar respuesta
    with st.chat_message("assistant"):
        if st.session_state.chain is None:
            answer = "No hay conexión con Neo4j. Verifica la configuración en el sidebar."
            st.markdown(answer)
        else:
            with st.spinner("Consultando el grafo..."):
                try:
                    result = ask(st.session_state.chain, prompt)
                    answer = result["answer"]
                    st.session_state.last_cypher = result["cypher"]
                    st.session_state.messages.append({"role": "assistant", "content": answer})
                    st.rerun()
                except Exception as exc:
                    answer = f"Error al consultar el grafo: {exc}"
                    st.error(answer)
                    st.session_state.messages.append({"role": "assistant", "content": answer})
