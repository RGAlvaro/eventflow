# Plan del hito 0

- `pyproject.toml` y `uv.lock`: versiones reproducibles de FastAPI, SQLAlchemy, Alembic, cliente Redis y herramientas de comprobación. P-01 cerrada.
- `src/eventflow/`: aplicación mínima, settings, conexiones y health checks. DSN por variables de entorno; sesiones de BD por proceso.
- `alembic/`: primera revisión con `organizations(id UUID, name, created_at)`; migración reversible. EF-01 exige organización en futuras filas.
- `compose.yaml` y `Dockerfile`: servicios locales PostgreSQL, Redis y API; sin publicar BD o Redis fuera de loopback.
- `tests/` y `.github/workflows/backend.yml`: pruebas unitarias y de integración en PostgreSQL real, migración limpia, Ruff y mypy. P-02 cerrada.
- `README.md`: comandos comprobados y límites de este corte.

Riesgos: disponibilidad del daemon Docker y acceso a paquetes en el entorno de ejecución. Si falta alguno, se ejecutarán las verificaciones posibles y se dejará el bloqueo medido en el estado del proyecto.
