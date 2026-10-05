# Primer recorrido backend

Hito 1. Requisitos afectados: EF-02, EF-04, EF-05, EF-08 y base de EF-01/EF-10/EF-11.

## Escenarios de aceptación

1. Una clave de publicación asociada a una organización envía `order.created`; la API valida cuerpo y tipo, selecciona solo suscripciones exactas y responde `202` con el ID tras confirmar en PostgreSQL evento, entregas y outbox en una transacción.
2. Una clave inválida o de otra organización no puede publicar ni leer datos ajenos. Una petición inválida o de más de 256 KiB no crea filas.
3. Con el broker caído después del commit, el evento sigue aceptado y el despachador publica el trabajo pendiente cuando Redis vuelve. Avisos duplicados no crean entregas duplicadas.
4. Un worker reclama una entrega con lease, firma los bytes enviados y registra el intento. Un receptor local de prueba verifica firma y responde 200; la entrega queda `succeeded` en PostgreSQL.
5. Si el aviso se pierde o un worker cae con lease vencido, el reconciliador reactiva la entrega desde PostgreSQL sin nueva petición de ingesta.
6. Una URL interna, una redirección o un cambio DNS no eluden la política de salida. HTTP local solo se permite al receptor de prueba configurado explícitamente.

## Límites del hito

- La idempotencia concurrente completa, política de reintentos, resultados tardíos y límites por endpoint se completan en hito 2. Las columnas y restricciones que los soportan se crean desde el primer esquema.
- Las credenciales de publicación y los endpoints se crean mediante fixtures de desarrollo; aún no hay API pública de gestión. No se expone este servicio a Internet.
- La entrega es *at least once*; el receptor debe tolerar duplicados. No se promete orden global.
