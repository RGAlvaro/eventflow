# Estado actual de EventFlow

Actualizado: 2026-10-07. Esta es una **foto breve del presente** para orientar la siguiente tarea; no almacena el historial. La secuencia prevista está en [roadmap.md](roadmap.md) y la actividad pasada en [implementation-log.md](implementation-log.md).

| Aspecto | Estado |
| --- | --- |
| Hito activo | Hito 3 en curso: seguridad y límites backend en `feat/hito3-backend-security`. |
| Último corte | `docs/work/hito3-backend-security/` abierto; diseño P-05/P-06 fusionado mediante PR #6. |
| Producto existente | Núcleo fiable del hito 2. En la rama activa se inició cifrado autenticado de secretos, migración 0004 y cabecera de versión; todavía no hay frontend ni gestión pública de claves y destinos. |
| Última evidencia | Rama actual: Ruff, formato y mypy correctos; 19 pruebas locales pasadas, 16 omitidas por falta de PostgreSQL. La última integración completa es CI de la PR #6 con 32 pruebas pasadas; aún no verifica esta rama. |
| Decisiones inmediatas | P-05/P-06 tienen contrato de diseño. La implementación P-05 está incompleta; gestión, rotación, límites y retención siguen pendientes. P-08 detallará bloqueo de salida y custodia de claves del VPS. |
| Bloqueos externos | Esta sesión WSL no tiene Docker integrado; las pruebas PostgreSQL/Redis y la migración aplicada requieren CI. El corte permanece abierto hasta verificarlas sin omisiones. |
| Próxima acción | Implementar y comprobar primero cifrado de secretos, versión de firma y migración; continuar con gestión autorizada y límites de ingesta. |

Actualiza esta tabla cuando cambie el hito, el corte, una capacidad comprobada, un bloqueo o la siguiente acción. Mantén el detalle de comandos, pruebas y motivos en la entrada correspondiente del log humano, sin copiar aquí su cronología.
