# Seeker Accounting

First safe implementation slice for the locked Seeker Accounting blueprints:

- Python
- PySide6 + Qt Widgets
- `src/` layout
- bootstrap and shell foundation
- centralized light/dark theme infrastructure
- placeholder workspaces only

## Scope in this slice

Included:

- application bootstrap pipeline
- runtime settings and logging
- database engine/session/unit-of-work foundation only
- shell with sidebar, topbar, and workspace host
- tokenized theme system with light/dark support

Not included:

- ORM business models
- Alembic revisions
- accounting workflows
- create/edit business forms

## Setup

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

## Run

```powershell
.\.venv\Scripts\seeker-accounting.exe
```

## Runtime notes

- Default runtime files are written to `.seeker_runtime/`.
- A local `.env` file can override theme, runtime root, log level, and database URL.
- On startup, the app applies pending Alembic migrations to the configured database before loading the shell.
