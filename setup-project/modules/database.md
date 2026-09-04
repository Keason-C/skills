# Database — PostgreSQL

- Production runs PostgreSQL 16. Migrations and SQL stay within PG 16 features; verify a migration against a `postgres:16` container (swap `DATABASE_URL`) before calling it done.
- Driver: asyncpg. ORM & migrations: SQLAlchemy 2.0 + Alembic — async engine and session throughout, Alembic included (`env.py` runs migrations via `run_sync`); table models in `Mapped[]` declarative style. Table models stay out of API signatures; the DB sits behind a connection-URL seam.
- Test database: the project's own call — settle it once (embedded server, container, or other) and record it in the project's stack notes.
