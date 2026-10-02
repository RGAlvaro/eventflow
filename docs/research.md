# Fuentes y criterio de adopción

Consultado el 2026-09-30 y revisado el 2026-10-01. Esta lista registra fuentes que cambiaron el harness; no sustituye documentación técnica actual al implementar una dependencia.

| Fuente | Hallazgo aplicado |
| --- | --- |
| [OpenAI Docs: AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md) | Codex carga la cadena de instrucciones al iniciar y el límite combinado por defecto es 32 KiB. Ese límite es un techo, no un tamaño óptimo; el `AGENTS.md` de este proyecto contiene solo reglas que hacen falta en toda tarea. |
| [OpenAI Docs: skills](https://learn.chatgpt.com/docs/build-skills) | Las skills se descubren en `.agents/skills` y su cuerpo se carga cuando se activan. Los procedimientos largos se colocan allí, con descripciones de activación precisas. |
| [GitHub Spec Kit](https://github.com/github/spec-kit) | El ciclo especificar → planificar → tareas → implementar → converger aporta trazabilidad. Se adopta una versión ligera por corte, sin instalar Spec Kit ni obligar a usarlo para cada bug. |
| [OWASP: prevención SSRF](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) | Desactivar redirecciones y validar direcciones IPv4/IPv6 y resolución DNS. La arquitectura exige además que la conexión use una IP validada y recomienda control de salida en despliegue. |
| [Celery: configuración de tareas](https://docs.celeryq.dev/en/stable/userguide/configuration.html) | `acks_late` no basta por sí solo para garantizar recuperación si muere un worker. Se fija una prueba de fallo real y PostgreSQL conserva el estado recuperable. |
| [RFC 9110: Retry-After](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3) | El campo admite segundos o fecha HTTP. El hito 2 prueba ambas formas, además de una cabecera inválida, antes de fijar la política de pausa por endpoint. |
| [Docker: instalación en Ubuntu](https://docs.docker.com/engine/install/ubuntu/) | Docker Engine admite Ubuntu 24.04 LTS. La documentación advierte que los puertos de contenedores publicados pueden eludir reglas UFW; la puerta del VPS exige comprobar exposición y egress reales. |
| [Docker: Compose en producción](https://docs.docker.com/compose/how-tos/production/) | Compose permite una topología de un solo servidor y configuración específica de producción; se adopta para la demo en VPS, con imágenes versionadas y reinicio documentado. |
| [Docker: secretos de Compose](https://docs.docker.com/reference/compose-file/secrets/) | Los secretos pueden concederse solo a los servicios que los necesitan; no se incluirán en Git ni en el bundle de frontend. |
| [Anthropic: evaluación de agentes](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) | Una evaluación define entrada, criterio y resultado observable. `harness-evals.md` comprueba decisiones del agente y se revisa con cambios del harness, sin añadir pruebas que solo cotejen frases. |

Las decisiones de outbox, lease, secretos y autorización backend son juicios de diseño de este proyecto basados en sus requisitos y riesgos. Su validez se comprobará con pruebas y puede revisarse mediante `decisions.md`. La sesión de la interfaz se decidirá en P-10 antes de construir la demo; Ubuntu 24.04 LTS y un solo VPS son requisitos del usuario.
