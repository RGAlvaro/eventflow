# Tareas

- [x] Implementar API de consulta paginada y detalles con autorización `manage`, filtros, índices y pruebas PostgreSQL; 46 pruebas sin omisiones en CI de PR #10.
- [x] Cerrar P-10 e implementar aprovisionamiento, sesión, límites de login, CSRF, revocación y auditoría; 49 pruebas sin omisiones en CI de PR #10.
- [x] Cerrar P-11 e implementar receptor controlado, cuatro escenarios, firma, deduplicación persistente y prueba con reclamo real del worker; 61 pruebas sin omisiones en local y PR #11 fusionada tras CI verde.
- [ ] Conectar observaciones sanitizadas del receptor a una ruta tenant autorizada de EventFlow y a los controles de escenarios de la UI.
  - [x] Configurar puente privado y ruta GET con autorización tenant y URL fija.
  - [x] Verificar SSRF, fallos de red y esquema de respuesta con pruebas HTTP/PostgreSQL.
  - [ ] Conectar controles de UI cuando exista frontend.
- [ ] Añadir logs, métricas y pruebas de redacción.
- [ ] Construir UI React responsive, pruebas de teclado/anchos y build en CI.
- [ ] Verificar recorridos E2E y suite completa sin omisiones, revisar fiabilidad, PR verde y merge.
