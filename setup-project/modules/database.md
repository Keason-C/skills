# Database

Defaults by workload; preserve existing project choices. Application and analytical stores may coexist. Table models stay separate from API contracts; connection settings live in configuration.

| Workload | Choice |
| --- | --- |
| Concurrent writers or deployed applications | PostgreSQL |
| Single-writer local tools, prototypes, or stateful CLIs | SQLite |
| File-based analytical queries and transformations | DuckDB for SQL; Polars for DataFrames |

## PostgreSQL

- Driver: asyncpg. ORM/migrations: SQLAlchemy 2.0 + Alembic, async engine/session, `Mapped[]` tables; Alembic uses `run_sync`.
- Local dev/test image: official `postgres:<major>`, matching production's major version. Version alignment alone does not cover production data, permissions, extensions, or lock contention.

## SQLite

- Local scripts/tools: sqlite3 + direct SQL; WAL for concurrent readers with one writer, aiosqlite for async access.
- Business applications: SQLAlchemy 2.0 + Alembic for ORM mapping and versioned schemas; `Mapped[]` tables, sync/async matching the application. PostgreSQL migration is a project decision when needed.

## DuckDB / Polars

- DuckDB: in-process SQL over files or a persistent database file. Polars: DataFrame transformations. Combine through Arrow where useful and supported; SQL/DataFrame APIs are the default, with ORM sharing only for a concrete need.

## Testing

- Persistence tests: isolated databases using the project's engine, covering relevant transactions, constraints, and migrations; external services mocked, async calls tested asynchronously.
- Data migrations: representative existing data, with permissions, extensions, and lock behavior considered where relevant.
