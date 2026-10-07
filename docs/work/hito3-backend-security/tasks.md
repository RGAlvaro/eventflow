# Tareas

- [x] Cifrar secretos de firma existentes y nuevos; migración 0004 y pruebas de autenticidad, ausencia de clave y conversión de datos previos.
- [x] Identificar versión de secreto en webhook y probar verificación de ambas versiones durante rotación, incluida recifra de la clave maestra.
- [x] Gestionar claves API y credencial `manage` con aprovisionamiento de operador, revocación y aislamiento de tenant.
- [x] Gestionar endpoints y suscripciones con política SSRF y cuotas transaccionales.
- [x] Autorizar replay de gestión y auditar actor y generación.
- [x] Aplicar bucket Redis, cuota diaria y capacidad pendiente con respuestas estables.
- [x] Purgar agregados terminales y comprobar que replay y trabajo pendiente impiden una purga indebida.
- [x] Revisar fiabilidad y ejecutar suite completa sin omisiones, migraciones, lint, tipos y CI en la PR #8.
