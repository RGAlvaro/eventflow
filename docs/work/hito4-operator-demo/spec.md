# Hito 4 — Operación e interfaz de demostración

Rama: `feat/hito4-observability-api`. Requisitos: EF-09, EF-10 y EF-11. Decisiones: P-07 cerrada; D-16/D-17 fijan las opciones de acceso y receptor, y P-10/P-11 concretarán sus contratos.

## Escenarios observables

1. Un actor `manage` consulta eventos, entregas e intentos de su organización con páginas estables, filtros exactos y detalles sanitizados. Una credencial `publish`, revocada o de otro tenant no lee datos. Un cursor inválido o de otro filtro/tenant se rechaza.
2. Desde una sesión de operador protegida, la interfaz publica ejemplos y muestra estados, intentos, próxima ejecución y replay obtenidos del backend real, con estados de carga/error/vacío, teclado y anchos de 360, 768 y 1280 px.
3. Un receptor controlado verifica la firma, registra solo datos sanitizados y ofrece escenarios 200, 503→200, 429 y fallo hasta `dead_lettered`. El operador puede repetirlos sin crear destinos internos arbitrarios.
4. Logs y métricas permiten seguir request, evento, entrega e intento sin exponer claves, secretos, cabeceras de autorización ni cuerpos de respuesta. Salud y guía operativa permiten diagnosticar dependencias.
5. La instalación y CI ejecutan pruebas y build del frontend además de la suite backend. El recorrido E2E usa PostgreSQL, Redis, worker y receptor reales.

## Puerta

Aceptación de EF-09 a EF-11: recorridos reales y accesibles, autorización tenant, redacción, backend y frontend verdes en CI, y ninguna prueba omitida. P-08 y la demo pública en VPS pertenecen al hito 6.
