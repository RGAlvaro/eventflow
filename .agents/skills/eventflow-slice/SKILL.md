---
name: eventflow-slice
description: Preparar e implementar un corte funcional de EventFlow con requisitos trazables, plan, tareas y verificación. Usar para funcionalidades o cambios transversales; no para correcciones pequeñas y localizadas.
---

# Corte funcional de EventFlow

Consulta `docs/project-state.md` y lee los IDs aplicables de `docs/spec.md`, los invariantes de `docs/architecture.md` y el hito de `docs/roadmap.md`. Inspecciona código y pruebas antes de planificar. No leas `docs/implementation-log.md` por rutina; está escrito para personas.

Antes de editar archivos de un corte, comprueba que el árbol está limpio, actualiza `main` desde `origin/main` y crea una rama nueva con nombre descriptivo. Si ya hay cambios ajenos, consérvalos y trabaja en una rama o worktree aislado sin sobrescribirlos. Anota la rama del corte en `docs/project-state.md` mientras esté activo.

Para un cambio suficientemente amplio, crea o actualiza `docs/work/<slug>/`:

1. `spec.md`: comportamiento y escenarios observables, requisitos EF afectados, casos de fallo y límites. No copies secciones enteras del dossier.
2. `plan.md`: archivos/componentes afectados, contrato de datos, migración, prueba, riesgos y decisiones P/D relevantes. Si una decisión bloquea corrección o seguridad, ciérrala en `docs/decisions.md` antes de codificar.
3. `tasks.md`: unidades pequeñas de implementación con prueba asociada y estado pendiente/hecho. Mantén la lista sincronizada con lo realizado.

Implementa un grupo pequeño de tareas, ejecuta las comprobaciones existentes y compara el resultado con cada escenario de `spec.md`. Añade tareas pendientes cuando la comparación descubra huecos.

Para cerrar el corte, ejecuta **todos** los tests del repositorio y todas las comprobaciones vigentes de CI, además de migraciones y escenarios de aceptación que correspondan. Usa PostgreSQL/Redis reales para que las pruebas de integración no se omitan; los comandos actuales están en `README.md` y `.github/workflows/`. Si aparece un test omitido, un fallo o una comprobación que no puedes ejecutar, resuélvelo y repite la suite completa. Registra resultados concretos en el log. No declares terminado el corte con verificación parcial.

Cuando todo pase, actualiza tareas, estado y log, revisa el diff, haz commit en la rama y push a `origin`. Abre una PR contra `main`, espera todas sus comprobaciones de CI y revisiones exigidas, corrige cualquier fallo en la misma rama y vuelve a verificar. Fusiona la PR solo cuando estén verdes y se cumplan los criterios del corte. Sin permisos de GitHub, CI disponible o posibilidad de merge, deja PR y corte abiertos, con el bloqueo en `project-state.md`; nunca sustituyas el merge por un push directo a `main`. Tras fusionar, sincroniza `main` local y comprueba que contiene el cambio.

Al cerrar trabajo significativo, deja `docs/project-state.md` con el hito, bloqueo y siguiente paso actuales y añade al `docs/implementation-log.md` una entrada breve para el usuario: cambio y motivo, comandos realmente ejecutados con resultado, y pendientes. Incluye el enlace de PR en la entrega final. La hoja de ruta describe el plan y no acumula estados diarios.

Para bugs acotados, diagnostica la causa, añade una prueba que reproduzca el síntoma cuando sea útil, corrige y verifica. No crees tres documentos de fase por rutina.
