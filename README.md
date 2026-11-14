# TaskForge AI — Backend Engine

> Autonomous AI Workflow Automation Platform with Human-in-the-Loop Orchestration, LangGraph DAG Execution, and Groq LLM Intelligence.

---

## 1. Project Overview

**TaskForge AI** is an enterprise-grade agentic AI orchestration platform designed to translate high-level natural language objectives into structured, dependency-aware Directed Acyclic Graphs (DAGs) and autonomously execute them using a rich ecosystem of sandboxed tools.

Key capabilities:
- **Natural Language Task Decomposition:** Evaluates user prompts into structured execution plans using Groq (`llama-3.3-70b-versatile`).
- **LangGraph Dynamic DAG Scheduling:** Computes topological levels and supports parallel and sequential step execution with state persistence.
- **Human-in-the-Loop (HITL) Security:** 8-state approval lifecycle, SHA-256 payload tampering detection, and strict RBAC authorization across 5 roles (`SUPER_ADMIN`, `WORKSPACE_OWNER`, `OPERATOR`, `REVIEWER`, `VIEWER`).
- **Autonomous Tool Execution:** Web research, PDF document generation (ReportLab), file extraction, summarization, and email dispatching with strict boundary enforcement.
- **Dual-Engine Persistence:** Zero-config SQLite local development and high-throughput connection-pooled PostgreSQL with Alembic migrations.

---

## 2. Backend Architecture

```
                       +-----------------------------+
                       |    FastAPI REST / WS API    |
                       +--------------+--------------+
                                      |
                     +----------------+----------------+
                     |                                 |
                     v                                 v
        +-------------------------+       +-------------------------+
        |   TaskAnalyzer & LLM    |       |  LangGraph Orchestrator |
        |  (Groq LLaMA 3.3 70B)   |       |   DAG State Machine     |
        +-------------------------+       +------------+------------+
                                                       |
                             +-------------------------+-------------------------+
                             |                         |                         |
                             v                         v                         v
                   +-------------------+     +-------------------+     +-------------------+
                   |   Tool Registry   |     |  Approval Policy  |     | State Checkpointer|
                   | PDF, Web, File... |     |  RBAC & Reviews   |     | SQLite / Postgres |
                   +-------------------+     +-------------------+     +-------------------+
```

---

## 3. Technology Stack

- **Framework:** FastAPI 0.115+
- **ASGI Server:** Uvicorn / Gunicorn
- **Agent Orchestration:** LangGraph 0.2+, LangChain Core 0.3+
- **LLM Provider:** Groq API (`llama-3.3-70b-versatile`)
- **Database ORM:** SQLAlchemy 2.0+
- **Database Migration:** Alembic 1.14+
- **Persistence:** SQLite 3 (local) / PostgreSQL 16 with `psycopg 3` (production)
- **Document & PDF Engine:** ReportLab 4.0+, PyPDF 5.0+
- **Validation:** Pydantic 2.9+, Pydantic Settings 2.6+
- **Testing:** Pytest 8.3+, Pytest-Asyncio 0.24+

---

## 4. Installation Instructions

### Prerequisites
- Python 3.11 or higher
- Git

### Setup Steps
```bash
# Clone the repository
git clone https://github.com/Roheithr07/TaskForgeAI-backend.git
cd TaskForgeAI-backend

# Create and activate virtual environment
python -m venv venv

# On Linux/macOS:
source venv/bin/activate
# On Windows (PowerShell):
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 5. Environment Configuration

Copy the example environment configuration:
```bash
cp .env.example .env
```

Configure your environment variables in `.env`:
```ini
# Application Mode
APP_NAME="TaskForge AI"
APP_ENV=development
APP_DEBUG=true
LOG_LEVEL=INFO
JSON_LOGS=false

# Security
SECRET_KEY=generate-a-secure-random-64-character-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Groq LLM API Key (Required for AI planning)
GROQ_API_KEY=gsk_your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile

# Database (Default: local SQLite; or PostgreSQL)
DATABASE_URL=sqlite:///./taskforge.db

# Frontend & CORS
FRONTEND_URL=http://localhost:5173
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173
```

---

## 6. Database Setup & Migrations

TaskForge AI uses Alembic for schema migrations:

```bash
# Initialize and apply all database migrations to latest revision
python migrate.py upgrade head

# Check current migration revision
python migrate.py current

# Rollback one migration step
python migrate.py downgrade -1
```

*Note: In development mode with SQLite, initial tables will also be auto-created on application startup if running for the first time.*

---

## 7. Running the FastAPI Application

### Development Mode (with hot-reload)
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Production Mode (multi-worker)
```bash
gunicorn -c gunicorn_conf.py app.main:app
# Or on Windows:
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

The backend server will start at: `http://localhost:8000`

---

## 8. API Documentation & Endpoints

Interactive Swagger UI and ReDoc are available in development mode:
- **Interactive OpenAPI Documentation:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Alternative ReDoc UI:** [http://localhost:8000/redoc](http://localhost:8000/redoc)

### Core API Endpoints Overview
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/health` | Liveness check & process uptime |
| `GET` | `/api/v1/ready` | Readiness probe (validates DB & artifacts storage) |
| `POST` | `/api/v1/planning/generate` | Decomposes prompt into structured execution plan |
| `POST` | `/api/v1/planning/validate` | Validates dependency DAG for cycles and missing tools |
| `POST` | `/api/v1/workflows` | Creates and persists a new workflow |
| `GET` | `/api/v1/workflows` | Lists all workflows with status and progress |
| `POST` | `/api/v1/workflows/{id}/execute`| Triggers autonomous LangGraph DAG execution |
| `GET` | `/api/v1/workflows/{id}/graph` | Returns DAG node/edge topology for visualization |
| `GET` | `/api/v1/workflows/{id}/checkpoints` | Lists persistent state snapshots |
| `GET` | `/api/v1/approvals` | Lists pending/reviewed human approval requests |
| `POST` | `/api/v1/approvals/{id}/approve` | Grants human authorization for sensitive action |
| `POST` | `/api/v1/approvals/{id}/reject` | Denies sensitive action execution |
| `GET` | `/api/v1/artifacts` | Lists generated PDFs, markdown, and reports |
| `GET` | `/api/v1/artifacts/{filename}` | Secure artifact download with path traversal defense |
| `GET` | `/api/v1/templates` | Lists production workflow templates |
| `GET` | `/api/v1/dashboard/metrics` | Live platform metrics and execution statistics |

---

## 9. Testing Instructions

The backend includes a comprehensive automated test suite covering unit, integration, security, and DAG orchestration tests.

```bash
# Run the entire test suite
pytest -v

# Run with short test summary
pytest -q

# Run specific milestone tests
pytest tests/test_milestone8_production.py -v
pytest tests/test_milestone5_security.py -v
pytest tests/test_milestone3_dag.py -v
```

---

## 10. License

MIT License. Designed and engineered for the Catalyst Hackathon.
