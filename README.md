# LabelGuard

LabelGuard is an AI-assisted package-label inspection system. It supports inspection work; its results are not legally binding enforcement decisions.

## Milestone 1: project foundation

Milestones 1–2 provide the foundation and data schema. Milestone 3 supports creating a draft inspection and safely uploading a JPG/JPEG/PNG package image (10 MB default limit); OCR and compliance workflows begin in later milestones.

## Prerequisites

- Python 3.11+
- Node.js 20+
- Docker Desktop (recommended for PostgreSQL)

## Run with Docker

1. Copy `.env.example` to `.env` and adjust values only if needed.
2. Run `docker compose up --build`.
3. Open `http://localhost:5173` for the frontend.
4. Open `http://localhost:8000/docs` for API documentation.

The backend health check is available at `GET http://localhost:8000/api/health`.

To create an inspection and upload an image, use the API docs at `http://localhost:8000/docs`. The upload endpoint is `POST /api/inspections/{inspection_id}/image` with multipart field name `image`.

## Run locally

Start PostgreSQL with `docker compose up db -d`, then in separate terminals run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn backend.app.main:app --reload
```

```powershell
cd frontend
npm install
npm run dev
```

Run backend tests with `pytest backend/tests`.

Apply database migrations after PostgreSQL is running:

```powershell
alembic -c backend/alembic.ini upgrade head
```

## Structure

```text
backend/       FastAPI application and Alembic configuration
frontend/      React/Vite application
database/      Database-related project files (migrations are under backend/alembic)
docker-compose.yml
```

## Environment

Copy `.env.example` to `.env`. Do not commit `.env`; it may contain credentials.
