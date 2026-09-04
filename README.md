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

LabelGuard runs one recognizer per configured language against the same image and removes exact duplicate text-box results. It validates configuration against the documented PP-OCRv3 language codes used by this project, so an unsupported code fails clearly at startup rather than being treated as supported.

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

## UI Languages

The interface offers 23 language options: English, Hindi, Assamese, Bengali, Bodo, Dogri, Gujarati, Kannada, Kashmiri, Konkani, Maithili, Malayalam, Manipuri (Meitei), Marathi, Nepali, Odia, Punjabi, Sanskrit, Santali, Sindhi, Tamil, Telugu, and Urdu. English is the fallback for any wording that does not yet have a reviewed translation. The header selector is accessible, persists under `labelguard-language`, and restores English when its stored value is invalid.

Translations live in `frontend/src/locales/`. Add a locale JSON file, register its code and native display name in `frontend/src/i18n.tsx`, and add reviewed translations incrementally; missing keys automatically use English.

## OCR Languages

The configured PP-OCRv3 languages are `en,hi,gom,mai,mr,ne,sa,ta,te,ur,ka`: English, Hindi, Konkani, Maithili, Marathi, Nepali, Sanskrit, Tamil, Telugu, Urdu, and Kannada. `ka` is PaddleOCR's Kannada model code. These recognizers are selected explicitly with `OCR_LANGUAGES`; the OCR response reports the actual configured codes used.

UI language support and OCR language support are separate. The interface can support languages that are not currently enabled for OCR. In particular, Assamese, Bengali, Bodo, Dogri, Gujarati, Kashmiri, Malayalam, Manipuri (Meitei), Odia, Punjabi, Santali, and Sindhi are UI options but are not listed as supported PP-OCRv3 language codes for this configuration. Do not translate OCR text: it remains the text printed on the package.

To add another OCR language later, first verify a compatible PaddleOCR model and its exact `lang` code for the installed release, then add that code to `SUPPORTED_PADDLE_OCR_LANGUAGES` and `OCR_LANGUAGES` and cover it with a unit test.

Run the frontend locally:

```powershell
cd frontend
npm install
npm run dev
```

Run its tests with `npm test`.

## Environment

Copy `.env.example` to `.env`. Do not commit `.env`; it may contain credentials.
