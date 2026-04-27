# Graphic design multi-agent studio — design spec

**Date:** 2026-04-24  
**Status:** Approved direction (conversation + explicit choices)

## Goal

Build a **web application** where a **supervisor-led multi-agent runtime** helps produce **AI-generated graphic concepts** (v1: image API), supports **human-in-the-loop** review (Approve / Try new / Modify), and on approval sends deliverables to a **client via Gmail using Google APIs (OAuth)**—not browser automation and not shared passwords.

A separate **marketing-oriented worker agent** proposes **bounded, policy-safe lead research** (assistive, human-approved), not unsupervised mass scraping of Google results.

## Non-goals (v1)

- Pixel-perfect clone of third-party brand packaging (trademark / trade dress risk).
- Fully autonomous cold outreach at scale.
- Multi-tenant agency onboarding, billing, or full CRM.

## User-facing flow

1. User creates a **design job** (brief: e.g. “chocolate wrapper, premium, minimalist”).
2. **Research worker** produces a **structured brief** and **safe reference set** (stock/licensed/user-uploaded; “inspired by category trends,” not copy-paste of famous packs).
3. **Designer worker** calls the **image generation API**; assets stored in object storage (or local disk in dev).
4. Web UI shows **large preview** and actions:
   - **Approve** → unlock send step  
   - **Try new** → new generation with adjusted creative direction  
   - **Modify** → user instruction → designer worker revises (new prompt / variation)
5. On **Approve**, user confirms **client email**, editable template for body (includes questions such as satisfaction / change requests).
6. **Email worker** sends message + attachments via **Gmail API** (user has completed OAuth in app).
7. **Marketing worker** (phase 1b): produces **draft** lead list / outreach snippets from **allowed inputs** (CSV import, curated URLs, Search API with quotas)—**requires user confirmation** before any send.

## Architecture: true multi-agent runtime (planner + workers)

### Roles

| Agent / module | Responsibility |
|----------------|----------------|
| **Planner (supervisor)** | Reads job state + latest worker results; decides next worker invocation; handles retries; stops at human gates. |
| **Research worker** | Gathers references → structured JSON brief + constraints for the designer. |
| **Designer worker** | Builds prompts; calls image API; records variants and metadata. |
| **Email worker** | Composes MIME; sends via Gmail API; logs message ids. |
| **Marketing worker** | Drafts lead hypotheses + message drafts; **no** auto-send. |

### Runtime pattern

- **Message bus:** async queue (Redis, or in-memory for local dev) carrying typed envelopes: `AgentTask`, `AgentResult`, `HumanGate` (approval pending).
- **State store:** durable job graph (Postgres/SQLite): job, status, artifacts, agent trace (append-only event log for audit).
- **Planner loop:** event-driven or poll-based; idempotent task ids; exponential backoff on external API failures.
- **Human gates:** planner transitions to `awaiting_review` / `awaiting_send_confirm`; web UI posts user decisions back as events.

### Web app

- **Frontend:** SPA (e.g. React + Vite) or Next.js; authenticates **you** (single-user v1: simple auth or local-only).
- **Backend:** HTTP API + websocket/SSE for job updates; never stores Google **passwords**—only **OAuth tokens** (encrypted at rest).

### Gmail integration

- **Google OAuth 2.0** with scopes limited to sending (and optionally read for threading later).
- **Refresh tokens** stored server-side, encrypted; rotate on revocation.

### Image generation

- v1: single provider abstraction (`ImageClient`) — implement one concrete adapter (e.g. OpenAI Images or other) behind env config.

### Compliance / safety

- **IP:** briefs must instruct models to avoid logos, trademarked mascots, and distinctive trade dress; human review before client send.
- **Marketing:** no credential sharing; no circumventing Google ToS; marketing worker outputs **drafts** for approval.

## Phasing

| Phase | Deliverable |
|-------|-------------|
| **P0** | Monorepo scaffold; planner + in-memory bus + stub workers; REST job + UI shell. |
| **P1** | Real image adapter + file storage; review UI wired to gates. |
| **P2** | Gmail OAuth + send with attachment. |
| **P3** | Marketing worker assist mode + import/Search API option. |

## Testing strategy

- Unit tests: message schema, planner transitions, idempotency keys.
- Contract tests: mock Gmail and image APIs.
- E2E (optional later): Playwright against local stack.

## Open decisions (implementation plan)

- Exact frontend stack (Vite React vs Next) and hosting.
- Queue backing (Redis vs in-proc for MVP).
- Which image API first (env-driven).
