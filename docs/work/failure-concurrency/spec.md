# Hito 2: fallos, duplicados y concurrencia

Requisitos: EF-02–EF-08 y EF-13. El estado durable y los intentos pertenecen a PostgreSQL; Redis solo avisa.

## Aceptación observable

1. Dos publicaciones simultáneas de una organización con el mismo `Idempotency-Key` y contenido semánticamente igual devuelven el mismo evento y generan un solo conjunto de entregas. Una clave reutilizada con contenido distinto devuelve `409`; otra organización puede reutilizarla.
2. Una entrega que recibe 503 dos veces y luego 200 conserva tres intentos numerados y próximos vencimientos en PostgreSQL. Errores de red, timeout, 408, 429 y 5xx se reintentan con backoff exponencial y jitter hasta siete intentos por generación; 3xx y 4xx restantes terminan.
3. Tras siete fallos reintentables, la entrega queda `dead_lettered`. Un comando interno con credencial de gestión del mismo tenant registra actor y nueva generación, crea trabajo recuperable y permite éxito sin borrar intentos anteriores. Una clave de publicación o de otro tenant no puede repetirla.
4. Dos workers o avisos duplicados no crean un intento duplicado ni superan capacidad agregada. Si vence un lease, el resultado tardío no pisa el nuevo estado. Un timeout después de que el receptor procese la petición puede causar otro envío físico con los mismos IDs y generación.
5. Los límites compartidos de P-09 se respetan entre workers. Un 429 con `Retry-After` en segundos o fecha HTTP pausa solo su endpoint, con máximo de una hora; el otro destino progresa. Una fecha o valor inválido usa backoff ordinario.
6. Una caída entre commit y publicación, la pérdida de un aviso o un worker muerto dejan la entrega recuperable sin nueva petición de ingesta.

## Límites

- El replay es solo un comando interno con credencial de gestión de fixture; su API pública y la gestión de claves pertenecen al hito 3.
- El receptor local controlado es de pruebas. No se expone el servicio a Internet; cifrado de secretos y egress del VPS siguen pendientes.
