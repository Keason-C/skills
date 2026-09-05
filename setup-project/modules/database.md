# Database

Pick by how the data is written — every row that applies, since one project can hold both an app database and an analytics store — and record the choice in the project's stack notes. Whatever is picked: table models stay out of API signatures, and each DB sits behind its own connection-URL seam, so a choice can flip later without touching callers.

| Ask | Answer |
| --- | --- |
| Several processes or users write at the same time, or it gets deployed | **PostgreSQL** |
| One process writes, row-level transactions — an internal tool, a prototype, a CLI with state | **SQLite** |
| The data arrives as files (CSV / Parquet) and the questions are aggregates | **DuckDB + Polars** |

## PostgreSQL

- Prod is a real PostgreSQL instance; dev and tests run the official `postgres:<major>` image at the same major — one version everywhere, so a migration verified against the container (swap `DATABASE_URL`) is verified for prod. Migrations and SQL stay within that major's features.
- Driver: asyncpg. ORM & migrations: SQLAlchemy 2.0 + Alembic — async engine and session throughout (`env.py` runs migrations via `run_sync`); table models in `Mapped[]` declarative style.

## SQLite

- One file, WAL mode. Driver: aiosqlite. The same SQLAlchemy 2.0 + Alembic + `Mapped[]` setup as PostgreSQL, so moving up later is a URL change.

## DuckDB + Polars

- One database file, in-process, no container. Driver: `duckdb`; DataFrames are Polars, exchanged with DuckDB through Arrow at zero copy. The code is SQL plus DataFrame calls — an ORM is the exception, not the default (`duckdb-sqlalchemy` when models must be shared with an app).
