---
name: eventflow-slice
description: Preparar e implementar un corte funcional de EventFlow con requisitos trazables, plan, tareas y verificación. Usar para funcionalidades o cambios transversales; no para correcciones pequeñas y localizadas.
---

# Corte funcional de EventFlow

Consulta `docs/project-state.md` y lee los IDs aplicables de `docs/spec.md`, los invariantes de `docs/architecture.md` y el hito de `docs/roadmap.md`. Inspecciona código y pruebas antes de planificar. No leas `docs/implementation-log.md` por rutina; está escrito para personas.

Para un cambio suficientemente amplio, crea o actualiza `docs/work/<slug>/`:

1. `spec.md`: comportamiento y escenarios observables, requisitos EF afectados, casos de fallo y límites. No copies secciones enteras del dossier.
2. `plan.md`: archivos/componentes afectados, contrato de datos, migración, prueba, riesgos y decisiones P/D relevantes. Si una decisión bloquea corrección o seguridad, ciérrala en `docs/decisions.md` antes de codificar.
3. `tasks.md`: unidades pequeñas de implementación con prueba asociada y estado pendiente/hecho. Mantén la lista sincronizada con lo realizado.

Implementa un grupo pequeño de tareas, ejecuta las comprobaciones existentes y compara el resultado con cada escenario de `spec.md`. Añade tareas pendientes cuando la comparación descubra huecos. Da por concluido el corte cuando los criterios sean observables y los comandos relevantes pasen; comunica límites de entorno en vez de declarar éxito sin prueba.

Al cerrar trabajo significativo, deja `docs/project-state.md` con el hito, bloqueo y siguiente paso actuales y añade al `docs/implementation-log.md` una entrada breve para el usuario: cambio y motivo, comandos realmente ejecutados con resultado, y pendientes. La hoja de ruta describe el plan y no acumula estados diarios.

Para bugs acotados, diagnostica la causa, añade una prueba que reproduzca el síntoma cuando sea útil, corrige y verifica. No crees tres documentos de fase por rutina.
