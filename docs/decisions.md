# Registro de decisiones

El dossier v0.1 es una propuesta generada por ChatGPT. Sus etiquetas `DECIDED` no vinculan este proyecto. Aquí se registran decisiones iniciales y cuestiones que se cerrarán antes de implementar la parte afectada. Cambios arquitectónicos posteriores pueden convertirse en ADR breves en `docs/adr/`.

| ID | Estado | Decisión y motivo |
| --- | --- | --- |
| D-01 | Aceptada | Monolito modular con FastAPI, workers Celery, PostgreSQL y Redis. Favorece un entorno local reproducible y mantiene separada la ejecución asíncrona. |
| D-02 | Aceptada | SQLAlchemy 2 y esquemas Pydantic separados; SQLModel no añade valor claro para este dominio. La API puede usar sesiones async y el worker elegir interfaz síncrona documentada. |
| D-03 | Aceptada | Outbox transaccional desde la primera ingestión. El dossier lo difería, pero un `202` con publicación directa tras commit deja entregas aceptadas sin camino de recuperación. La comparación con el enfoque ingenuo se documentará como análisis, sin desplegarlo primero. |
| D-04 | Aceptada | PostgreSQL conserva estados, intentos y vencimientos; Redis/Celery solo activan trabajo. Se requiere reconciliador para trabajo que quedó sin aviso o con lease vencido. |
| D-05 | Aceptada | Las entregas se reclaman con transición y lease respaldados por PostgreSQL, sin mantener la transacción durante HTTP. La entrega física duplicada sigue siendo posible. |
| D-06 | Sustituida | La propuesta temprana de JWT en memoria para el dashboard queda reemplazada por P-10: la interfaz ahora forma parte del MVP, pero la sesión debe elegirse junto con su modelo de protección y pruebas. |
| D-07 | Aceptada | Mismo `Idempotency-Key` con cuerpo/tipo distintos produce `409`; se guarda fingerprint. Sin clave, dos peticiones iguales son dos eventos válidos. |
| D-08 | Aceptada | Replay usa la misma entrega, nueva generación de intentos y registro del actor. Mantiene historia y unicidad evento/endpoint. |
| D-09 | Aceptada | No almacenar previews de respuesta webhook por defecto. Los cuerpos pueden incluir datos sensibles y no son necesarios para el diagnóstico básico. |
| D-10 | Aceptada | SSRF se resuelve antes de enviar a destinos controlados por usuarios, no en un hito de endurecimiento posterior. Validación DNS y control de la IP de conexión se complementan con bloqueo de salida. |
| D-11 | Aceptada | El primer worker ya usa reclamo con lease y reconciliación desde PostgreSQL para entregas pendientes o vencidas, aunque Celery marque un aviso como publicado. El hito 2 amplía su semántica y pruebas de concurrencia. |
| D-12 | Aceptada | La firma v1 cubre timestamp en segundos Unix y bytes exactos del cuerpo enviado; los IDs de evento/entrega y la generación son estables en reintentos, la generación sube en replay y el timestamp se renueva en cada intento. El receptor puede limitar antigüedad y deduplicar por entrega y generación. |
| D-13 | Aceptada | Los límites de envío se aplican entre todos los workers por endpoint y globalmente; una respuesta 429 puede pausar solo su endpoint. PostgreSQL conserva el momento de reintento y pausa; los valores y algoritmo se cierran en P-09. |
| D-14 | Aceptada | El MVP final incluye interfaz responsive y demo técnica en un único VPS Ubuntu 24.04 LTS. Docker Compose conserva la topología API/worker/despachador/PostgreSQL/Redis; el proxy HTTPS sirve la UI y es el único punto público. Se completará el backend fiable antes de construir la interfaz. |

## Decisiones por cerrar

| ID | Momento | Pregunta y criterio |
| --- | --- | --- |
| P-01 | Cerrada (2026-10-02) | `uv` con `pyproject.toml` y `uv.lock`; `uv sync --locked` fija instalación local y CI. Alternativa: Poetry. Se eligió `uv` por estar disponible en el entorno y permitir un único lock verificable. Consecuencia: CI instala una versión fijada de `uv`; se comprueba instalación limpia. |
| P-02 | Cerrada (2026-10-02) | PostgreSQL y Redis mediante Compose en local y servicios equivalentes en CI; pruebas de integración usan PostgreSQL real, nunca SQLite. Alternativa: Testcontainers. Esta opción evita depender del socket Docker dentro de pytest y reproduce la topología local. Se comprueban migración a BD vacía y consultas reales. |
| P-03 | Antes de salida HTTP | Mecanismo concreto de resolución/conexión segura con httpx, política de puertos y egress en despliegue. Probar DNS rebinding y IPv6; si no se puede garantizar, restringir destinos mediante allowlist. |
| P-04 | Hito 1, antes del primer worker | Duración/renovación de lease y parámetros Celery (`acks_late`, pérdida de worker, prefetch, visibilidad Redis). Ensayar parada abrupta y duplicados; PostgreSQL debe permitir recuperación aunque Celery no reentregue. |
| P-05 | Antes de producción | Cifrado de secretos webhook, rotación, recuperación y separación de llaves por entorno. |
| P-06 | Antes de exposición pública | Algoritmo y cuota de rate limit, límites de tamaño, política de retención, autorización fina de replay y respuesta al agotamiento de capacidad. |
| P-07 | Hito 4 | Paginación de eventos/entregas y contrato de filtros; escoger cursor cuando el volumen/orden lo justifique. |
| P-08 | Hito 5, antes del VPS | Elegir proveedor/dominio, tamaño medido del VPS Ubuntu 24.04, certificado TLS, mecanismo de secretos, backup/restauración y reglas reales de egress. La elección del sistema operativo y topología de un solo VPS ya está cerrada. |
| P-09 | Antes del hito 2 | Algoritmo y umbrales de ritmo/concurrencia de salida global y por endpoint; parseo y cota de `Retry-After` en segundos o fecha HTTP; tratamiento de reloj y espera máxima. Probar con varios workers y un destino sano junto a otro limitado. |
| P-10 | Hito 4, antes de la interfaz | Sesión del operador de demo, expiración, protección CSRF, provisión/revocación y alcance de la credencial de gestión. No fijar JWT ni almacenamiento del token sin probar el flujo del navegador; nunca exponer claves API brutas en el bundle. La matriz completa de roles sigue fuera del MVP. |
| P-11 | Hito 4, antes del receptor de demo | Fijar conectividad y aislamiento del receptor controlado en local y VPS, sus modos 200/503/429/fallo y su aprovisionamiento seguro. La UI no permitirá configurar destinos internos arbitrarios ni saltarse la política SSRF. |

Para cerrar una cuestión, añade fecha, opción, alternativas, consecuencias y prueba que respalda la decisión. No generes ADRs vacíos solo para cubrir un número del dossier.
