# Database

Pick by how the data is written — every row that applies, since one project can hold both an app database and an analytics store. Record only decision rationale that code and configuration do not explain in the project's stack notes. Keep table models out of API signatures and connection settings in configuration. Add storage abstractions when current requirements justify them.

| Ask | Answer |
| --- | --- |
| Several processes or users write at the same time, or it gets deployed | **PostgreSQL** |
| One process writes, row-level transactions — an internal tool, a prototype, a CLI with state | **SQLite** |
| The data arrives as files (CSV / Parquet) and needs analytical queries or transformations | **DuckDB** for SQL; **Polars** for DataFrames; combine when both are needed |

## PostgreSQL

- Dev and tests run the official `postgres:<major>` image at the same major as production. This checks version compatibility; production migration behavior also depends on existing data, permissions, extensions, and lock contention. For migrations that transform existing data, verify the result on representative data in an isolated test database; assess these other factors when the migration depends on them.
- Driver: asyncpg. ORM & migrations: SQLAlchemy 2.0 + Alembic — async engine and session throughout (`env.py` runs migrations via `run_sync`); table models in `Mapped[]` declarative style.

## Database tests

- For changes to persistence behavior or schema, test the relevant transactions, constraints, and migrations against an isolated database using the project's actual engine. Mock external services while exercising the database behavior being verified. Use async tests for async database calls.

## SQLite

- Small scripts and local tools: start with the standard-library sqlite3 driver and direct SQL. Use WAL when concurrent readers and a writer need it; use aiosqlite when the application needs async access.
- Persistent business applications: use SQLAlchemy 2.0 + Alembic when ORM mapping and versioned schema changes are needed; use `Mapped[]` for ORM tables. Choose sync or async to match the application. Design a PostgreSQL migration when it becomes a concrete requirement.

## DuckDB / Polars

- DuckDB: in-process SQL analytics via `duckdb`, querying files directly or using a database file when persistence is needed. Polars: DataFrame transformations. Install the tool the workload needs; combine them when the same workflow benefits from both, exchanging data through Arrow where supported. Use SQL and DataFrame APIs directly; add an ORM only for a concrete model-sharing requirement.
