# Database Migrations (Alembic)

This project uses [Alembic](https://alembic.sqlalchemy.org/) for database schema management. Think of it as **version control for your database** — each migration describes a schema change, and Alembic tracks which ones have already been applied.

## How it works

- On startup, the app container runs `alembic upgrade head` **before** starting the server. Pending migrations are applied automatically.
- Applied migrations are tracked in the `alembic_version` table, so they never run twice.
- Each migration has an `upgrade()` and `downgrade()` function for applying and reverting changes.

## Common commands

Run these inside the app container (`docker compose exec app sh`):

```bash
# Apply all pending migrations
alembic upgrade head

# Revert the last migration
alembic downgrade -1

# Show current migration
alembic current

# Show migration history
alembic history
```

## Creating a new migration

```bash
# Generate a new migration script
alembic revision -m "describe your change here"
```

This creates a file in `migrations/versions/`. Edit the `upgrade()` and `downgrade()` functions, then restart the app or run `alembic upgrade head`.
