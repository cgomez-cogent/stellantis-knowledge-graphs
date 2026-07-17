# stellantis-knowledge-graphs

Tools for building and querying code knowledge graphs. The main project in this repo is **[kg-chatbot](kg-chatbot/)**: it indexes any codebase into a knowledge graph (Neo4j) and lets you ask questions about it in natural language.

```
"What services depend on AuthModule?"
"How does the payment flow work?"
"What files import the UserRepository class?"
```

**Stack:** LightRAG · Neo4j · LangChain · Gemini 2.0 Flash (free tier) · Streamlit

## Repo structure

```
stellantis-knowledge-graphs/
├── kg-chatbot/              Main project (see its README for the full guide)
│   ├── app.py               Streamlit UI
│   ├── ingest/               Indexing pipeline (Python, TS/JS, Terraform, AST)
│   ├── graph/                Graph connection and visualization (Neo4j)
│   ├── chatbot/              Question/answer chain (LangChain)
│   └── docker-compose.yml    Local Neo4j
└── callouts_extractor.py    Standalone utility to extract "callouts" from XML
```

## Quick start

The whole workflow lives inside `kg-chatbot/`. Minimum steps to get it running:

```bash
cd kg-chatbot

# 1. Configure environment variables
cp .env.example .env
# Edit .env with your GOOGLE_API_KEY and a NEO4J_PASSWORD

# 2. Start Neo4j
docker compose up -d
# Neo4j browser available at http://localhost:7474

# 3. Install Python dependencies
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 4. Index a codebase
python -m ingest.pipeline /path/to/your/project

# 5. Launch the chatbot
streamlit run app.py
# UI available at http://localhost:8501
```

### Prerequisites

- Python 3.10+
- Docker (for local Neo4j)
- A free Gemini API key ([aistudio.google.com](https://aistudio.google.com/app/apikey))

For the full guide (environment variables, migration to Amazon Neptune, example questions, module-by-module structure), see **[kg-chatbot/README.md](kg-chatbot/README.md)**.
