# MaterialsPEML Lab

**MaterialsPEML Lab is an AI-driven R&D platform for polymer-modified plastics (kingfa domain).**

> 中文版见 [README.md](README.md)

---

## Overview

Starting from a one-sentence R&D goal, it automates the closed loop: candidate screening → formulation design → process planning → approval → experiment validation → strategy feedback.

Key principles:

- A four-tier data credibility model (measured / simulated / predicted / estimated) that answers "where did this value come from and how trustworthy is it"
- Closed-loop ECML experimentation with a validation accuracy ruler (predicted vs. actual MAPE)
- Domain packs defining default material systems, formulation templates, and reference ranges
- Enterprise features: multi-tenant access control, fine-grained approvals, and full audit tracing

## Tech Stack

- **Backend**: FastAPI + SQLAlchemy + PostgreSQL (`postgresql+psycopg://...`), with Alembic migrations
- **Frontend**: Vue 3 + Vite + Ant Design Vue 4
- **Intelligence**: LLM (InternLM, etc.) + MCP scientific tools (SCP) + local generators/predictors
- **Tests**: pytest (backend) + Playwright (frontend E2E audits)

## Quick Start

```bash
# Backend (port 8200)
python -m uvicorn battery_materials_agent.api:app --host 0.0.0.0 --port 8200

# Frontend (Vite, port 5173)
cd frontend && npm install && npm run dev

# Production build
cd frontend && npm run build
```

Database:

```
postgresql+psycopg://batteryemcl:batteryemcl_dev@localhost:5433/batteryemcl
```

## Running Tests

```bash
# Backend unit tests
python -m pytest tests/unit/test_two_layer_workflow.py tests/unit/test_process_deepening_service.py -q

# Frontend E2E audits (requires both 5173 + 8200 running)
cd frontend && node tests/deep-audit.mjs
```

## Repository Layout

```
battery_materials_agent/     # Backend FastAPI service
  agent.py                   #   BatteryMaterialsAgent facade + MCP tool registration
  api.py                     #   REST API (monolithic app entry)
  experiment/               #   Candidate/process/equipment/experiment-controller stores
  generation/               #   Candidate generators (crystal/polymer)
  ecml/                      #   ECML closed-loop engine
  hybrid/                    #   R&D pipeline orchestration
  domain_packs/              #   Domain packs (battery / kingfa)
frontend/                    # Vue 3 frontend
alembic/versions/            # Database migrations
docs/                        # Product manual, user guide, ADR design decisions
tests/unit/                  # pytest unit tests
```

## Contact

Interested in this project, collaboration, or a commercial license? Reach out at:

**wangmiao.chen@cheeryell.com**

## License

[PolyForm Noncommercial License 1.0.0](LICENSE) — noncommercial use only; commercial use requires a separate license.
