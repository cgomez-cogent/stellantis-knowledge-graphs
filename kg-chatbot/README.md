# KG Chatbot — Knowledge Graph Chatbot for your Codebase

Index any codebase into a knowledge graph and ask it questions in natural language.

```
"What services depend on AuthModule?"
"How does the payment flow work?"
"What files import the UserRepository class?"
```

**Stack:** LightRAG · Neo4j · LangChain · Gemini 2.0 Flash (free tier) · Streamlit

---

## Quick Start

### 1. Start Neo4j

```bash
# Copy the configuration file
cp .env.example .env
# Edit .env with your GOOGLE_API_KEY and choose a NEO4J_PASSWORD

docker compose up -d
# Neo4j browser available at http://localhost:7474
```

### 2. Install Python dependencies

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 3. Index your codebase

```bash
# Point to the root directory of your project
python -m ingest.pipeline /path/to/your/project

# Example:
python -m ingest.pipeline ../my-api
```

The process prints progress file by file and may take several minutes
depending on the codebase size and Gemini API limits.

### 4. Launch the chatbot

```bash
streamlit run app.py
```

The UI opens at http://localhost:8501

---

## Point to a different codebase

From the app **sidebar** you can enter any path and click
**"Start ingestion"** to re-index without leaving the interface.

Or from the terminal:

```bash
python -m ingest.pipeline ./other-project
```

Supported file types: `.py` `.ts` `.js` `.md` `.txt`

Automatically ignored directories: `node_modules`, `.git`, `__pycache__`,
`dist`, `build`, `.venv`

---

## Migration to Amazon Neptune

To use Amazon Neptune in production instead of local Neo4j,
**just change these 3 environment variables** in your `.env` — no code
changes required:

```bash
# Step 1: Update the endpoint
NEO4J_URI=bolt+s://<your-cluster>.neptune.amazonaws.com:8182

# Step 2: Configure IAM credentials (or leave empty if using IAM auth)
NEO4J_USER=
NEO4J_PASSWORD=

# Step 3: Restart the app
streamlit run app.py
```

Neptune is compatible with the Bolt protocol and Cypher via the
`neo4j-python-driver`, which is exactly what LangChain and LightRAG use.

---

## Example questions

Once your codebase is indexed, you can ask things like:

| Question | Type |
|----------|------|
| What modules does `UserService` import? | Dependencies |
| What files define API endpoints? | Structure |
| How is `PaymentController` connected to the database? | Flow |
| What classes extend `BaseRepository`? | Inheritance |
| What functions call `sendEmail`? | References |
| Where is JWT authentication handled? | Semantic search |

---

## Environment variables

| Variable | Description | Required |
|----------|-------------|----------|
| `GOOGLE_API_KEY` | Gemini API key (free at [aistudio.google.com](https://aistudio.google.com/app/apikey)) | Yes |
| `NEO4J_URI` | Bolt connection URI | Yes |
| `NEO4J_USER` | Neo4j username | Yes |
| `NEO4J_PASSWORD` | Neo4j password | Yes |
| `NEO4J_DATABASE` | Database name (default: `neo4j`) | No |
| `LIGHTRAG_WORKING_DIR` | LightRAG cache directory (default: `./lightrag_cache`) | No |

---

## Project structure

```
kg-chatbot/
├── docker-compose.yml    Local Neo4j
├── .env.example          Configuration template
├── requirements.txt      Python dependencies
├── graph/
│   └── store.py          Neo4j connection factory
├── ingest/
│   ├── loaders.py        Codebase file reader
│   └── pipeline.py       Ingestion pipeline (entry point)
├── chatbot/
│   ├── memory.py         Conversation memory
│   └── chain.py          GraphCypherQAChain + helper ask()
└── app.py                Streamlit UI
```
