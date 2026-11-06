# A2 - Clasificación de eventos auditd mediante LLM local

## Descripción

Proyecto de investigación y desarrollo para evaluar si un modelo de lenguaje
ejecutado localmente puede clasificar eventos de auditoría de Linux generados
por auditd según su nivel de riesgo y distinguir actividades legítimas de
actividades sospechosas.

El procesamiento se realizará localmente, sin enviar registros a servicios
externos.

## Objetivo

Comparar la clasificación realizada por modelos de lenguaje locales con una
alternativa basada en expresiones regulares, evaluando la calidad de las
predicciones y el costo computacional.

## Alcance

- Captura de eventos mediante auditd.
- Generación de escenarios controlados y datos etiquetados.
- Agrupación y procesamiento de registros por evento de auditoría.
- Anonimización de información y preparación de datos.
- Clasificación mediante reglas y modelos de lenguaje locales.
- Evaluación con precisión, recall, F1 y métricas de rendimiento.

## Estructura

- `audit/`: reglas de auditoría.
- `scripts/`: automatización y generación de escenarios.
- `data/`: datos originales y procesados.
- `src/`: código fuente del proyecto.
- `prompts/`: instrucciones utilizadas por los modelos.
- `results/`: resultados de las evaluaciones.
- `evidencias/`: capturas y evidencias técnicas.
- `tests/`: pruebas del proyecto.

## Tecnologías previstas

- Ubuntu Server 24.04 LTS.
- auditd.
- Python.
- Ollama.
- Modelos de lenguaje ejecutados localmente.
- Git y GitHub.

## Estado

Proyecto en etapa de preparación del entorno.
