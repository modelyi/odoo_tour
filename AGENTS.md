# AGENTS.md

This file provides guidance to the AI agent when working with code in this repository.

## Project Structure

Phase-based repository with Chinese folder names. Letter prefix enforces ordering — preserve exactly:

| Folder | Phase |
|--------|-------|
| `a-调研` | Research (completed) |
| `b-蓝图` | Blueprint — architecture, business specs (BS-XX), tech design |
| `c-系统实现` | Implementation — Odoo 19 modules, Docker, deploy scripts |
| `d-交付验收` | Delivery & acceptance — test reports, user manuals |

Do not create new top-level phase folders. Place artifacts in the phase they belong to.

## Tech Stack

**Odoo 19** + PostgreSQL 16 + Redis 7 + Docker + Nginx (tms.solepro.cloud).
All custom modules are in `c-系统实现/tms-platform/addons/tour_*`.

## Build & Run

```bash
cd c-系统实现/tms-platform
make up          # docker compose up -d
make install     # install tour_product module
make update      # update tour_product module (-u)
make reload      # restart Odoo to pick up code changes
make odoo-shell  # interactive Odoo Python shell (db: tms)
make db-shell    # psql -U odoo into tms-db
```

Container names: `tms-odoo`, `tms-db`, `tms-redis`. Module install/update uses `--stop-after-init`.

## Conventions

- **Language**: All documentation and communication defaults to Chinese unless specified otherwise.
- **Module naming**: `tour_*` (e.g., `tour_base`, `tour_product`, `tour_order`). Version format: `19.0.0.x.0`.
- **Business specs**: `b-蓝图/业务规格/BS-XX-*.md` are the source of truth for business logic. Consult the relevant BS before implementing features.
- **INDEX.md**: Master project index — update when adding/removing documents.
- **Scripts**: `c-系统实现/tms-platform/scripts/` contains one-off migration, diagnostic, and fix scripts (not part of module code).
- **Sensitive data**: `.env` and `et_cookies.json` are gitignored. Never commit secrets.
