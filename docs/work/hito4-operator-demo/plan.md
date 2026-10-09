# Plan breve

1. Cerrar P-07 e implementar consultas `manage` de eventos, entregas e intentos. Cursor por tiempo e ID, filtros exactos, índices y pruebas PostgreSQL de páginas/tenant. Este primer corte no requiere sesión de navegador.
2. Cerrar P-10 y añadir usuario/sesión de operador en PostgreSQL, límite Redis de login, cookie opaca, expiración, revocación y protección CSRF. Ampliar la auditoría y probar el flujo HTTP antes de conectar controles de UI.
3. Cerrar P-11 y construir receptor de demo como servicio externo independiente, con archivo privado de rutas y secretos, verificación de firma, deduplicación SQLite y observación sanitizada con token de servidor. Probar cuatro modos y envío con worker real. El proxy HTTPS y dominio público se validarán en P-08/hito 6.
4. Añadir observabilidad sanitizada y API de escenarios; construir React responsive, pruebas de accesibilidad/recorridos y build en CI.
5. Ejecutar la puerta completa, revisar fiabilidad y cerrar la PR. El despliegue y las reglas de red del VPS se verificarán en hito 6.

Riesgos: filtros o cursores sin tenant pueden filtrar datos; una sesión del navegador que reutilice la clave `manage` puede exponerla; un receptor local no debe ampliar la excepción SSRF de producción. P-10 y P-11 se cerraron antes de sus implementaciones. El receptor externo se dedica a una sola organización de demo; el backend deberá mediar su consulta y comprobar ese tenant antes de exponer observaciones al navegador.
