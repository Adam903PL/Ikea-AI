# IKEA AI

Web application for turning furniture STEP/STP CAD files into IKEA-style assembly instructions.

The project has two parts:
- `backend/` - FastAPI + CadQuery/OpenCASCADE pipeline for STEP processing, mesh generation, parts extraction, SVG generation, assembly planning, and PDF export
- `frontend/` - Next.js UI for upload, 3D preview, parts 2D review, and assembly instruction browsing

## What It Does

### Stage 1
- upload a STEP/STP file
- process the model on the backend
- stream progress with SSE
- render backend-generated mesh data in a 3D viewer

### Stage 2
- extract solids from the STEP model
- classify parts as `panel`, `connector`, or `other`
- generate IKEA-style SVG drawings for part groups
- group repeated small parts by dimensions and volume tolerance

### Stage 3
- build a contact graph from processed geometry
- generate assembly preview assets
- ask OpenRouter for structured assembly steps
- validate the AI response and fall back to a deterministic planner when needed
- render step-by-step SVG instructions
- export the full instruction set to PDF

## Tech Stack

- Frontend: Next.js, React, TypeScript, Three.js, React Three Fiber
- Backend: Python, FastAPI
- CAD processing: CadQuery, OpenCASCADE
- AI provider: OpenRouter
- PDF/SVG tooling: ReportLab, svglib, CairoSVG

## Repository Layout

```text
.
├── backend
│   ├── app
│   ├── tests
│   └── uploads
├── frontend
│   ├── app
│   ├── public
│   └── types
└── vercel.json
```

## Environment Variables

### Backend

Copy `backend/.env.example` to `backend/.env`.

Required for AI planning:

```env
OPENROUTER_API_KEY=your_openrouter_api_key_here
```

Optional overrides:

```env
OPENROUTER_MODEL=google/gemini-2.5-pro
OPENROUTER_FALLBACK_MODEL=anthropic/claude-sonnet-4.5
OPENROUTER_HTTP_REFERER=http://127.0.0.1:3000
OPENROUTER_APP_TITLE=IKEA Builder
```

### Frontend

Copy `frontend/.env.example` to `frontend/.env.local`.

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

## Local Setup

### Backend

Use the CadQuery-ready virtual environment or install dependencies manually:

```bash
cd backend
pip install -r requirements.txt
```

Run the API:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --env-file .env
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend proxies browser API traffic through Next.js, so local CORS is much less brittle during development.

## Main API Endpoints

### Stage 1
- `POST /api/step/upload`
- `GET /api/progress/{job_id}/stream`
- `GET /api/step/mesh/{object_name}`

### Stage 2
- `POST /api/step/parts-2d`
- `GET /api/step/parts-2d/{object_name}`
- `GET /api/step/parts-2d/{object_name}/svg/{file_name}`

### Stage 3
- `POST /api/step/assembly-analysis`
- `GET /api/step/assembly/{object_name}`
- `GET /api/step/assembly/{object_name}/svg/{file_name}`
- `GET /api/step/assembly/{object_name}/pdf`

## Tests

Backend:

```bash
cd backend
python -m unittest discover -s tests
```

Frontend:

```bash
cd frontend
npm run lint
npm run build
```

## Notes

- The backend is the source of truth for processed geometry and generated artifacts.
- `backend/uploads/` is intentionally ignored except for `.gitkeep`.
- If OpenRouter is not configured or returns invalid output, the app falls back to deterministic assembly planning.
