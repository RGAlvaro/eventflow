# Plan breve

1. Cerrar P-07 e implementar consultas `manage` de eventos, entregas e intentos. Cursor por tiempo e ID, filtros exactos, índices y pruebas PostgreSQL de páginas/tenant. Este primer corte no requiere sesión de navegador.
2. Cerrar P-10 y añadir usuario/sesión de operador en PostgreSQL, límite Redis de login, cookie opaca, expiración, revocación y protección CSRF. Ampliar la auditoría y probar el flujo HTTP antes de conectar controles de UI.
3. Cerrar P-11 y construir receptor de demo controlado con verificación de firma, deduplicación y modos seguros; probarlo con worker real.
4. Añadir observabilidad sanitizada y API de escenarios; construir React responsive, pruebas de accesibilidad/recorridos y build en CI.
5. Ejecutar la puerta completa, revisar fiabilidad y cerrar la PR. El despliegue y las reglas de red del VPS se verificarán en hito 6.

Riesgos: filtros o cursores sin tenant pueden filtrar datos; una sesión del navegador que reutilice la clave `manage` puede exponerla; un receptor local no debe ampliar la excepción SSRF de producción. P-10 está cerrado antes de implementarlo; P-11 se concretará antes del receptor.
