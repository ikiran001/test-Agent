# Graphic Studio (MVP P0)

Multi-agent graphic design orchestration scaffold: planner + stub workers, SQLite job store, FastAPI review API.

## Setup

```bash
cd graphic_studio
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run API

```bash
export GRAPHIC_STUDIO_DB="$(pwd)/graphic_studio.db"
uvicorn graphic_studio.api.main:app --reload --app-dir .
```

(`--app-dir .` keeps imports stable when run from `graphic_studio/`.)

## Try it

```bash
curl -s -X POST localhost:8000/jobs -H 'content-type: application/json' -d '{"brief":"chocolate wrapper, premium"}'
curl -s localhost:8000/jobs/<id>
curl -s -X POST localhost:8000/jobs/<id>/action -H 'content-type: application/json' -d '{"action":"approve"}'
```

## Tests

```bash
cd graphic_studio
pytest -q
```

Design spec: `docs/superpowers/specs/2026-04-24-graphic-design-multi-agent-design.md`  
Implementation plan: `docs/superpowers/plans/2026-04-24-graphic-design-multi-agent-mvp.md`
