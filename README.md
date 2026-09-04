# LabelGuard

LabelGuard is an AI-assisted package-label inspection system. It supports inspection work; its results are not legally binding enforcement decisions.

## Milestone 1: project foundation

Milestones 1–3 provide the foundation, data schema, and safe package-image upload. Milestone 4 adds PaddleOCR text detection; field extraction and compliance workflows begin in later milestones.

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

## OCR

PaddleOCR requires the `paddlepaddle`, `paddleocr`, and OpenCV packages declared in `pyproject.toml`. CPU inference is the default; consult PaddlePaddle's installation guidance if your platform needs a platform-specific wheel or GPU support.

English and Hindi are enabled by default through `OCR_LANGUAGES=en,hi`. LabelGuard runs one recognizer per configured language against the same image and removes exact duplicate text-box results. Add later PaddleOCR language codes as a comma-separated value, for example `OCR_LANGUAGES=en,hi,mr`; no code changes are required.

After applying migrations and uploading an image, run OCR with:

```powershell
Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/api/inspections/<inspection-id>/images/<image-id>/ocr"
```

The response contains only OCR data, for example:

```json
{
  "engine": "PaddleOCR",
  "languages": ["en", "hi"],
  "raw_text": "MRP Rs 50",
  "results": [{"text": "MRP Rs 50", "confidence": 0.96, "bbox": [[10, 20], [110, 20], [110, 45], [10, 45]]}]
}
```

Model downloads may occur the first time PaddleOCR processes an image. The endpoint is `POST /api/inspections/{inspection_id}/images/{image_id}/ocr`.

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

## Website languages

The React interface supports English (default) and Hindi. The header language selector changes supported interface text without a page reload and stores the selection in browser `localStorage` under `labelguard-language`; refreshes retain the chosen language. OCR text is never translated because it is evidence returned by the API.

Translations live in `frontend/src/locales/en.json` and `frontend/src/locales/hi.json`. To add a language, add a locale JSON file with the same keys, register its code in `frontend/src/i18n.tsx`, and add it to the selector. Hindi and English use left-to-right layout.

Run the frontend locally:

```powershell
cd frontend
npm install
npm run dev
```

Run its tests with `npm test`.

## Environment

Copy `.env.example` to `.env`. Do not commit `.env`; it may contain credentials.
