# Hito 3 — Seguridad y límites backend

Rama: `feat/hito3-backend-security`. Requisitos: EF-01, EF-02, EF-04, EF-07, EF-08 y EF-10. Decisiones: P-05 y P-06 en `docs/decisions.md`.

## Escenarios observables

1. Una organización crea, lista y revoca claves de publicación; el valor bruto solo aparece al crearla. Una clave revocada deja de publicar. Una credencial de publicación no administra configuración ni replay.
2. Un actor de gestión administra destinos y suscripciones de su organización. No puede leer, mutar ni solicitar replay de otro tenant. La URL pasa la política SSRF también en cada envío.
3. El secreto de firma se guarda cifrado y la cabecera `X-EventFlow-Key-Id` identifica su versión. El worker no envía si la clave de cifrado falta o el texto cifrado está alterado; la entrega sigue recuperable sin agotar intentos. La rotación del secreto y de la clave maestra conserva el servicio y la auditoría según P-05.
4. La ingesta aplica un bucket compartido por organización, cuota diaria y capacidad pendiente. Al exceder un límite responde `429` o `503` según P-06 sin confirmar trabajo parcial. Una repetición idempotente aceptada previamente conserva su resultado incluso al alcanzar la cuota diaria.
5. La purga conserva todo el agregado mientras exista una entrega no terminal y borra agregados terminales al vencer el plazo; replay reinicia el plazo. La clave de idempotencia puede reutilizarse después de la purga.

## Puerta de aceptación

Pruebas de PostgreSQL y Redis reales para concurrencia, fallos, tenant, rotación, `429`/`503`, replay y purga; migración a base limpia y con datos previos; suite completa sin omisiones; Ruff, formato y mypy; PR y CI verdes. Las cifras iniciales se medirán antes de exposición pública en el hito 5.
