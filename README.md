# EventFlow

EventFlow es un proyecto de portfolio sobre ingestión de eventos y entrega de webhooks firmados. Su objetivo es mostrar cómo conservar y observar entregas asíncronas cuando hay fallos de red, duplicados, reintentos o workers interrumpidos.

## Estado actual

El proyecto está en el **hito 1, pendiente de implementación**. Ya existe la base backend del hito 0: una API FastAPI con endpoints de salud, configuración por entorno, migración inicial en PostgreSQL, servicios locales PostgreSQL/Redis con Docker Compose y comprobaciones automatizadas en GitHub Actions.

La ingesta de eventos, el worker de entregas, los webhooks firmados, la interfaz y la demo en VPS **aún no están implementados**. Las garantías que se describen a continuación son objetivos del diseño, no capacidades disponibles hoy.

## Qué construirá

- Aceptar un evento solo cuando sus datos y el trabajo recuperable estén confirmados en PostgreSQL.
- Entregar webhooks firmados y conservar el estado de cada intento, incluso ante fallos de Redis o de un worker.
- Gestionar duplicados, reintentos, aislamiento por organización y límites de ingesta y salida.
- Mostrar el recorrido real desde una interfaz adaptable a móvil y escritorio y ofrecer una demo en un VPS Ubuntu 24.04 LTS.

La secuencia y los criterios observables de cada hito están en la [hoja de ruta](docs/roadmap.md). La [especificación](docs/spec.md) define los requisitos y la [arquitectura](docs/architecture.md) describe las garantías técnicas previstas.

## Probar la base disponible

La [guía de desarrollo](docs/development.md) contiene los requisitos, pasos de arranque, migraciones y comprobaciones locales. En el estado actual se pueden iniciar la API y sus servicios y consultar `/health/live` y `/health/ready`; todavía no hay un endpoint para publicar eventos ni una demo pública.
