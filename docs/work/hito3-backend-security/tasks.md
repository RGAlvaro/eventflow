# Tareas

- [ ] Cifrar secretos de firma existentes y nuevos; utilidad, migración y pruebas de autenticidad/ausencia de clave escritas. Falta probar migración con datos previos en PostgreSQL.
- [ ] Identificar versión de secreto en webhook y probar receptor durante rotación. La cabecera se emite; faltan rotación y prueba de receptor.
- [ ] Gestionar claves API y credencial `manage` con revocación y tenant.
- [ ] Gestionar endpoints y suscripciones con SSRF y cuotas.
- [ ] Autorizar replay público y auditar actor.
- [ ] Aplicar bucket Redis, cuota diaria y capacidad pendiente con respuestas estables.
- [ ] Purgar agregados terminales y probar carreras con replay.
- [ ] Ejecutar revisión de fiabilidad, suite completa, migraciones, lint, tipos, CI y merge.
