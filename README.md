# Seeker Accounting

Seeker Accounting is a PySide6 desktop accounting application with a SQLite
runtime database, SQLAlchemy models, Alembic migrations, and service-layer
workflows for multi-company finance operations.

The current application includes foundations and working slices for company
setup, chart and fiscal controls, journals, sales, purchases, treasury,
inventory, fixed assets, taxation, reporting, administration, backups,
licensing, and Cameroon payroll workflows.

## Setup

```powershell
python -m pip install -e .
```

## Run

```powershell
seeker-accounting
```

On startup, the app creates runtime directories and applies pending Alembic
migrations to the configured database before loading the shell.

## Runtime

Default runtime files are written under `.seeker_runtime/`:

- `data/` contains the SQLite database and user-managed assets.
- `logs/` contains application logs.
- `config/` contains local configuration such as license and trial state.

A project `.env` file or process environment can override:

- `SEEKER_RUNTIME_ROOT`
- `SEEKER_DATABASE_URL`
- `SEEKER_THEME`
- `SEEKER_LOG_LEVEL`
- `SEEKER_CURRENT_USER`
- `SEEKER_TELEMETRY_ENABLED`

## Quality Checks

Useful local checks before shipping a change:

```powershell
python -m compileall -f -q src tests
python -c "import seeker_accounting.app.dependency.service_registry; import seeker_accounting.app.dependency.factories"
alembic check
pytest -q
```

Install pre-commit hooks to run the fast guardrails automatically:

```powershell
pre-commit install
```
