# KG Chatbot — Knowledge Graph Chatbot para tu Codebase

Indexa cualquier codebase en un grafo de conocimiento y hazle preguntas en lenguaje natural.

```
"¿Qué servicios dependen de AuthModule?"
"¿Cómo funciona el flujo de pagos?"
"¿Qué archivos importan la clase UserRepository?"
```

**Stack:** LightRAG · Neo4j · LangChain · Gemini 2.0 Flash (free tier) · Streamlit

---

## Quick Start

### 1. Levantar Neo4j

```bash
# Copia el archivo de configuración
cp .env.example .env
# Edita .env con tu GOOGLE_API_KEY y elige un NEO4J_PASSWORD

docker compose up -d
# Neo4j browser disponible en http://localhost:7474
```

### 2. Instalar dependencias Python

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 3. Indexar tu codebase

```bash
# Apunta al directorio raíz de tu proyecto
python -m ingest.pipeline /ruta/a/tu/proyecto

# Ejemplo:
python -m ingest.pipeline ../mi-api
```

El proceso imprime el progreso archivo por archivo y puede tardar varios minutos
dependiendo del tamaño del codebase y los límites de la API de Gemini.

### 4. Lanzar el chatbot

```bash
streamlit run app.py
```

La UI abre en http://localhost:8501

---

## Apuntar a un codebase diferente

Desde la **sidebar** de la app puedes ingresar cualquier ruta y hacer clic en
**"Iniciar ingesta"** para re-indexar sin salir de la interfaz.

O desde la terminal:

```bash
python -m ingest.pipeline ./otro-proyecto
```

Los archivos soportados son: `.py` `.ts` `.js` `.md` `.txt`

Carpetas ignoradas automáticamente: `node_modules`, `.git`, `__pycache__`,
`dist`, `build`, `.venv`

---

## Migración a Amazon Neptune

Para usar Amazon Neptune en producción en lugar de Neo4j local,
**solo cambia estas 3 variables de entorno** en tu `.env` — no se requiere
ningún cambio en el código:

```bash
# Paso 1: Actualiza el endpoint
NEO4J_URI=bolt+s://<tu-cluster>.neptune.amazonaws.com:8182

# Paso 2: Configura credenciales IAM (o déjalas vacías si usas IAM auth)
NEO4J_USER=
NEO4J_PASSWORD=

# Paso 3: Reinicia la app
streamlit run app.py
```

Neptune es compatible con el protocolo Bolt y Cypher via el driver
`neo4j-python-driver`, que es exactamente lo que usan LangChain y LightRAG.

---

## Preguntas de ejemplo

Una vez indexado tu codebase, puedes preguntar cosas como:

| Pregunta | Tipo |
|----------|------|
| ¿Qué módulos importa `UserService`? | Dependencias |
| ¿Qué archivos definen endpoints de la API? | Estructura |
| ¿Cómo está conectado `PaymentController` con la base de datos? | Flujo |
| ¿Qué clases extienden `BaseRepository`? | Herencia |
| ¿Qué funciones llaman a `sendEmail`? | Referencias |
| ¿Dónde se maneja la autenticación JWT? | Búsqueda semántica |

---

## Variables de entorno

| Variable | Descripción | Requerida |
|----------|-------------|-----------|
| `GOOGLE_API_KEY` | API key de Gemini (gratis en [aistudio.google.com](https://aistudio.google.com/app/apikey)) | Sí |
| `NEO4J_URI` | URI de conexión Bolt | Sí |
| `NEO4J_USER` | Usuario de Neo4j | Sí |
| `NEO4J_PASSWORD` | Contraseña de Neo4j | Sí |
| `NEO4J_DATABASE` | Base de datos (default: `neo4j`) | No |
| `LIGHTRAG_WORKING_DIR` | Carpeta de caché de LightRAG (default: `./lightrag_cache`) | No |

---

## Estructura del proyecto

```
kg-chatbot/
├── docker-compose.yml    Neo4j local
├── .env.example          Template de configuración
├── requirements.txt      Dependencias Python
├── graph/
│   └── store.py          Fábrica de conexiones Neo4j + LightRAG
├── ingest/
│   ├── loaders.py        Lector de archivos del codebase
│   └── pipeline.py       Pipeline de ingesta (entry point)
├── chatbot/
│   ├── memory.py         Memoria de conversación
│   └── chain.py          GraphCypherQAChain + helper ask()
└── app.py                Streamlit UI
```
