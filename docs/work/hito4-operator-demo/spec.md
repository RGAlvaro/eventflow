# Hito 4 — Operación e interfaz de demostración

Rama principal: `feat/hito4-observability-api`; P-11 se fusionó desde `feat/hito4-demo-receiver` y el puente de observaciones se implementa en `feat/hito4-receiver-observations`. Requisitos: EF-04, EF-09, EF-10 y EF-11. Decisiones: P-07, P-10 y P-11 cerradas; D-17 fija receptor HTTPS externo.

## Escenarios observables

1. Un actor `manage` consulta eventos, entregas e intentos de su organización con páginas estables, filtros exactos y detalles sanitizados. Una credencial `publish`, revocada o de otro tenant no lee datos. Un cursor inválido o de otro filtro/tenant se rechaza.
2. Desde una sesión de operador protegida, la interfaz publica ejemplos y muestra estados, intentos, próxima ejecución y replay obtenidos del backend real, con estados de carga/error/vacío, teclado y anchos de 360, 768 y 1280 px.
   La sesión se inicia con usuario y contraseña propios, vence y puede revocarse; las mutaciones con cookie exigen CSRF. La auditoría identifica al operador sin exponer una clave API al navegador.
3. Un receptor controlado verifica la firma, registra solo datos sanitizados y ofrece escenarios 200, 503→200, 429 y fallo hasta `dead_lettered`. El operador puede repetirlos sin crear destinos internos arbitrarios.
   Cada ruta externa está preconfigurada con un secreto propio y acepta solo solicitudes con HMAC v1, timestamp reciente e IDs/generación coincidentes. Reintentos de una generación ya procesada no vuelven a procesarla; un replay usa otra generación. El receptor sobrevive a reinicio y permite consultar el resultado solo con un token de servidor, sin exponer payload ni secretos. El fallo continuo de generación 1 pasa a 200 tras replay en generación 2.
   `GET /api/v1/management/deliveries/{id}/receiver-observation` comprueba primero la credencial y la organización de la entrega en PostgreSQL. Solo para endpoints de demo fijados en configuración privada consulta el origen HTTPS preconfigurado con un token de servidor; valida de nuevo DNS/IP pública antes de conectar, no sigue redirecciones ni proxies, limita tiempo y cuerpo, y devuelve únicamente campos sanitizados. Un tenant ajeno o una clave `publish` no provoca ninguna consulta al receptor. Una configuración o respuesta inválida y un receptor caído producen error controlado sin revelar token ni URL interna.
4. Logs y métricas permiten seguir request, evento, entrega e intento sin exponer claves, secretos, cabeceras de autorización ni cuerpos de respuesta. Salud y guía operativa permiten diagnosticar dependencias.
5. La instalación y CI ejecutan pruebas y build del frontend además de la suite backend. El recorrido E2E usa PostgreSQL, Redis, worker y receptor reales.

## Puerta

Aceptación de EF-09 a EF-11: recorridos reales y accesibles, autorización tenant, redacción, backend y frontend verdes en CI, y ninguna prueba omitida. P-08 y la demo pública en VPS pertenecen al hito 6.
