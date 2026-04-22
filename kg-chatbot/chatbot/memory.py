"""
Memoria de conversación para el chatbot.

Guarda las últimas 10 preguntas/respuestas de la sesión actual.
Se reinicia al recargar la app (es memoria en RAM, no persistente).
"""

from langchain.memory import ConversationBufferWindowMemory


def get_memory() -> ConversationBufferWindowMemory:
    return ConversationBufferWindowMemory(
        k=10,                    # ventana de los últimos 10 turnos
        memory_key="chat_history",
        return_messages=True,    # retorna objetos HumanMessage/AIMessage
        output_key="result",
    )
