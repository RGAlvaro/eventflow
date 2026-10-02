---
name: eventflow-reliability-review
description: Revisar cambios de EventFlow en ingesta, entregas, workers, autenticación o webhooks para detectar pérdida de trabajo, duplicados, cruces de tenant y riesgos SSRF. Usar antes de cerrar un cambio que toque esas rutas.
---

# Revisión de fiabilidad

Inspecciona el diff, pruebas y contratos de `docs/spec.md` y `docs/architecture.md`. Busca fallos demostrables en las rutas afectadas, especialmente:

- commit sin trabajo recuperable, publicación duplicada o trabajo vencido sin reconciliación;
- reclamos concurrentes, leases expirados, intento duplicado o transición ilegal;
- resultado tardío de un intento que pisa el estado del propietario actual del lease, o aviso publicado que queda sin recuperación;
- llamada HTTP realizada dentro de una transacción larga;
- clave de idempotencia reutilizada con datos distintos o carrera entre peticiones;
- acceso cruzado entre organizaciones, credenciales registradas o cuerpos de respuesta persistidos;
- URL aparentemente válida que conecta con una IP privada, redirección o proxy no previsto;
- destino con 429 o lento que supera el límite agregado por endpoint o bloquea entregas a destinos sanos;
- tests que solo comprueban mocks y no el fallo de PostgreSQL/Redis/worker relevante.

Informa primero hallazgos concretos con archivo, escenario de fallo y prueba que falta. Si no encuentras un problema, indica qué escenarios examinaste y cuáles no pudiste verificar. No conviertas esta lista en una orden para reescribir código no relacionado.
