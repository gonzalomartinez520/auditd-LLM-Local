
# A2 — Clasificación de eventos auditd mediante LLM locales

Proyecto experimental de **Sistemas Operativos y Redes 2** orientado a clasificar eventos de auditoría de Linux según la presencia de amenazas y su nivel de severidad.

Se compara un clasificador determinista basado en expresiones regulares con dos modelos de lenguaje ejecutados localmente mediante Ollama:

- **Qwen3 0.6B**
- **Gemma 3 1B**

El experimento incluye captura de registros, generación de escenarios controlados, normalización, etiquetado, selección de estrategias de prompting y evaluación de resultados.

Todo el procesamiento de los eventos se realiza localmente, sin enviarlos a servicios externos.

---

## 1. Objetivos

### Objetivo general

Evaluar la capacidad de modelos de lenguaje ejecutados localmente mediante CPU para clasificar eventos de auditoría de Linux, comparando su desempeño con un clasificador basado en expresiones regulares y analizando su costo computacional.

### Objetivos específicos

- Registrar eventos mediante el subsistema Linux Audit (`auditd`).
- Generar escenarios controlados de actividad legítima y sospechosa.
- Reconstruir eventos completos agrupando registros asociados a un mismo identificador `timestamp:serial`.
- Preparar una representación normalizada común para los clasificadores.
- Implementar un clasificador determinista mediante expresiones regulares.
- Ejecutar Qwen3 y Gemma localmente mediante Ollama.
- Comparar estrategias zero-shot, few-shot y chain-of-thought.
- Evaluar precisión, recall, F1, severidad, latencia, memoria y repetibilidad.
- Analizar falsos positivos, falsos negativos y limitaciones del experimento.

**Alcance:** se trata de un experimento controlado, no de un sistema de detección desplegado en producción.

---

## 2. Tecnologías utilizadas

| Tecnología | Uso |
|---|---|
| Ubuntu Server 24.04 LTS | Sistema operativo experimental |
| VirtualBox | Virtualización y aislamiento |
| Linux Audit (auditd) | Recolección de eventos |
| auditctl, ausearch y aureport | Configuración y consulta de auditoría |
| Python 3 | Procesamiento, clasificación y evaluación |
| Expresiones regulares | Clasificador determinista |
| Ollama 0.40.16 | Ejecución local de los LLM |
| Qwen3 0.6B | Clasificación mediante LLM |
| Gemma 3 1B | Clasificación mediante LLM |
| Git y GitHub | Versionado y reproducibilidad |

### Entorno experimental

El experimento se desarrolló en una máquina virtual Ubuntu Server 24.04 LTS con:

- Arquitectura x86_64.
- Kernel Linux 6.8.
- Aproximadamente 11 GiB de RAM.
- 4 GiB de swap.
- Volumen raíz de 29 GiB.
- Ejecución de modelos exclusivamente mediante CPU.

El rendimiento puede variar según el hardware del equipo utilizado para reproducir las pruebas.

---

## 3. Estructura del proyecto

```text
auditd-LLM-Local/
├── audit/
│   └── 99-a2.rules
│
├── scripts/
│   └── Scripts de generación de escenarios
│
├── src/
│   ├── procesar_audit.py
│   ├── clasificador_regex.py
│   ├── clasificador_regex_multiclase.py
│   ├── config_llm_a2.py
│   ├── prompts_llm.py
│   ├── prompts_fewshot_fijo.py
│   ├── preparar_fewshot_fijo.py
│   ├── evaluar_prompts_dev.py
│   ├── evaluar_fewshot_fijo_dev.py
│   ├── comparar_prompts_dev.py
│   ├── auditar_contexto_llm.py
│   ├── verificar_pretest_a2.py
│   ├── verificar_modelos_a2.py
│   ├── inferir_test_a2.py
│   ├── auditar_corridas_test_a2.py
│   ├── inferir_regex_test_a2.py
│   ├── analizar_test_a2.py
│   ├── analizar_errores_a2.py
│   └── seleccionar_errores_a2.py
│
├── data/
│   ├── raw/
│   └── processed/
│       └── dataset/
│
├── results/
│   ├── llm_dev/
│   ├── llm_test/
│   ├── regex_test/
│   └── analisis_final/
│
├── docs/
│   ├── criterios_severidad.md
│   └── protocolo_test_a2.json
│
├── evidencias/
│
└── README.md
```

La estructura representa los principales componentes utilizados durante el experimento.

**Importante:** algunos archivos y directorios de datos pueden estar excluidos del repositorio mediante `.gitignore`, por lo que no necesariamente estarán disponibles después de clonarlo.

---

## 4. Instalación

### 4.1. Requisitos previos

Se recomienda utilizar Ubuntu Server 24.04 LTS en una máquina virtual o entorno Linux de pruebas autorizado.

Es necesario contar con:

- Python 3.
- Git.
- Linux Audit.
- Ollama.
- Memoria suficiente para ejecutar los modelos locales.
- Acceso al repositorio del proyecto.

### 4.2. Clonar el repositorio

```bash
git clone <URL_DEL_REPOSITORIO>
cd auditd-LLM-Local
```

Reemplazar `<URL_DEL_REPOSITORIO>` por la dirección correspondiente en GitHub.

### 4.3. Instalar dependencias del sistema

Actualizar los repositorios:

```bash
sudo apt update
```

Instalar las herramientas principales:

```bash
sudo apt install -y \
  git \
  python3 \
  python3-venv \
  python3-pip \
  auditd \
  audispd-plugins
```

Comprobar las instalaciones:

```bash
python3 --version
git --version
```

### 4.4. Preparar Python

Opcionalmente, crear un entorno virtual:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Si el repositorio contiene dependencias adicionales en `requirements.txt`, instalarlas mediante:

```bash
python3 -m pip install -r requirements.txt
```

Los clasificadores y evaluadores principales utilizan módulos de la biblioteca estándar de Python.

### 4.5. Instalar Ollama

Instalar Ollama siguiendo las instrucciones oficiales:

https://ollama.com/download/linux

Verificar la instalación:

```bash
ollama --version
```

Descargar los modelos:

```bash
ollama pull qwen3:0.6b
ollama pull gemma3:1b
```

Comprobar los modelos disponibles:

```bash
ollama list
```

Para reproducir exactamente el experimento se utilizó:

```text
Ollama: 0.40.16
Qwen3:0.6b: 7df6b6e09427
Gemma3:1b: 97558784bdc9
```

Los identificadores permiten comprobar que se utilizan las versiones correspondientes.

Ollama debe estar disponible localmente en:

```text
http://127.0.0.1:11434
```

Si está instalado como servicio, puede comprobarse mediante:

```bash
systemctl status ollama
```

---

## 5. Configuración de auditoría

Para generar nuevas capturas es necesario habilitar auditd.

```bash
sudo systemctl enable --now auditd
```

Copiar las reglas del proyecto:

```bash
sudo cp audit/99-a2.rules \
  /etc/audit/rules.d/99-a2.rules
```

Cargar las reglas:

```bash
sudo augenrules --load
```

Verificar su estado:

```bash
sudo auditctl -s
sudo auditctl -l
```

Las reglas permiten registrar:

- Ejecuciones de programas mediante `execve` y `execveat`.
- Lecturas de `/etc/passwd` y `/etc/shadow`.
- Modificaciones en `/etc/sudoers` y `/etc/sudoers.d/`.

Los registros se almacenan normalmente en:

```text
/var/log/audit/audit.log
```

**Advertencia:** estas reglas y los escenarios experimentales deben utilizarse únicamente en un entorno de pruebas autorizado. Los registros de auditoría pueden contener información sensible.

---

## 6. Preparación del conjunto de datos

### 6.1. Captura y generación de escenarios

El conjunto experimental se construyó combinando:

- Eventos normales del funcionamiento de Ubuntu Server.
- Escenarios legítimos de administración.
- Escenarios controlados de actividad sospechosa.

Las variantes utilizadas fueron:

| Escenario | Descripción | Referencia |
|---|---|---|
| NORMAL | Actividad habitual del sistema | Legítima |
| E1 | Consultas de información | Legítima |
| E2 | Reconocimiento y autenticación sospechosa | Amenaza |
| E3a | Actualización administrativa | Legítima |
| E3b_control | Operaciones de control de identidad | Legítima |
| E3b_ataque | Anomalías simuladas de privilegios | Amenaza |
| E4a | Modificación administrativa autorizada | Legítima |
| E4b | Modificación sospechosa simulada | Amenaza |
| E5a | Accesos administrativos a archivos sensibles | Legítima |
| E5b | Accesos sospechosos a credenciales | Amenaza |

Los escenarios fueron ejecutados en un entorno controlado.

### 6.2. Procesamiento de registros

Los eventos originales fueron agrupados utilizando la marca temporal y el número de serie.

Una misma operación puede producir distintos registros, como:

```text
SYSCALL
EXECVE
PATH
CWD
PROCTITLE
```

Estos registros se relacionan mediante su identificador de auditoría.

Para procesar las capturas normales se utilizó:

```bash
python3 src/procesar_audit.py
```

El script requiere los archivos originales y las marcas temporales correspondientes a las capturas.

También se implementaron procedimientos de consolidación, normalización y división del dataset.

La normalización produjo una representación textual compacta, común para regex y los LLM.

### 6.3. Dataset final

Se obtuvieron **519 eventos únicos**.

| Clasificación | Eventos |
|---|---:|
| Legítimos | 409 |
| Sospechosos | 110 |
| Total | 519 |

Distribución por severidad:

| Nivel | Eventos |
|---|---:|
| INFO | 409 |
| BAJO | 0 |
| MEDIO | 90 |
| ALTO | 20 |

El nivel BAJO forma parte de la taxonomía, pero no tiene ejemplos reales en el dataset.

### 6.4. Separación desarrollo/test

El dataset se dividió en:

| Conjunto | Eventos | Finalidad |
|---|---:|---|
| Desarrollo | 158 | Selección de prompts |
| Test | 361 | Evaluación final |

Los archivos principales se encuentran en:

```text
data/processed/dataset/desarrollo.jsonl
data/processed/dataset/prueba.jsonl
data/processed/dataset/etiquetas_multiclase.csv
```

No existen identificadores compartidos entre desarrollo y prueba.

Sin embargo, 329 de los 361 eventos de test (91,14 %) presentan textos normalizados previamente observados en desarrollo.

Esta característica limita las conclusiones sobre generalización a comportamientos desconocidos.

---

## 7. Clasificadores implementados

### 7.1. Clasificador regex

Se implementó un clasificador determinista que identifica patrones específicos asociados con:

- Ejecución de `su`.
- Autenticaciones fallidas.
- Diferencias sospechosas entre UID y EUID.
- Accesos a `/etc/shadow` mediante `cat` o `cp`.

El clasificador devuelve un JSON con:

```json
{
  "amenaza": true,
  "nivel": "MEDIO",
  "tipo": "autenticacion",
  "explicacion": "Descripcion del indicador detectado"
}
```

### 7.2. Clasificadores LLM

Se utilizaron:

```text
qwen3:0.6b
gemma3:1b
```

Los modelos se ejecutaron mediante Ollama, exclusivamente sobre CPU.

Configuración utilizada:

```json
{
  "temperature": 0,
  "seed": 42,
  "num_ctx": 4096,
  "num_predict": 256
}
```

Se evaluaron tres estrategias:

- Zero-shot.
- Few-shot.
- Chain-of-thought.

La estrategia seleccionada para ambos modelos fue **few-shot fijo**.

Los ejemplos utilizados procedían exclusivamente del conjunto de desarrollo.

---

## 8. Ejecución del experimento

Todos los comandos deben ejecutarse desde la raíz del repositorio.

**Importante:** los scripts de evaluación pueden impedir sobrescribir archivos de resultados existentes. No deben repetirse si se desea conservar las evidencias originales.

Para reproducir las métricas originales es necesario disponer de los datos procesados y del protocolo few-shot utilizado durante desarrollo.

### 8.1. Evaluación de prompts en desarrollo

Ejecutar zero-shot:

```bash
python3 src/evaluar_prompts_dev.py \
  --modelo qwen3:0.6b \
  --prompt zero_shot

python3 src/evaluar_prompts_dev.py \
  --modelo gemma3:1b \
  --prompt zero_shot
```

Ejecutar chain-of-thought:

```bash
python3 src/evaluar_prompts_dev.py \
  --modelo qwen3:0.6b \
  --prompt chain_of_thought

python3 src/evaluar_prompts_dev.py \
  --modelo gemma3:1b \
  --prompt chain_of_thought
```

Preparar el protocolo few-shot fijo:

```bash
python3 src/preparar_fewshot_fijo.py
```

Evaluar few-shot fijo:

```bash
python3 src/evaluar_fewshot_fijo_dev.py \
  --modelo qwen3:0.6b

python3 src/evaluar_fewshot_fijo_dev.py \
  --modelo gemma3:1b
```

Comparar las estrategias:

```bash
python3 src/comparar_prompts_dev.py
```

Auditar los tokens y el contexto:

```bash
python3 src/auditar_contexto_llm.py
```

Los resultados se almacenan en:

```text
results/llm_dev/
```

### 8.2. Verificaciones previas a test

Verificar la integridad del protocolo:

```bash
python3 src/verificar_pretest_a2.py
```

Verificar las versiones de los modelos:

```bash
python3 src/verificar_modelos_a2.py
```

También se implementó una auditoría de solapamiento entre desarrollo y prueba:

```bash
python3 src/auditar_solapamiento_a2.py
```

### 8.3. Ejecución de Qwen3 sobre test

Primero puede comprobarse la configuración sin realizar inferencias:

```bash
python3 src/inferir_test_a2.py \
  --modelo qwen3:0.6b \
  --corrida 1 \
  --preflight
```

Ejecutar las tres corridas:

```bash
python3 src/inferir_test_a2.py \
  --modelo qwen3:0.6b \
  --corrida 1

python3 src/inferir_test_a2.py \
  --modelo qwen3:0.6b \
  --corrida 2

python3 src/inferir_test_a2.py \
  --modelo qwen3:0.6b \
  --corrida 3
```

Para mantener condiciones iniciales comparables, se recomienda descargar los modelos entre corridas:

```bash
ollama stop qwen3:0.6b
```

### 8.4. Ejecución de Gemma sobre test

Verificar la configuración:

```bash
python3 src/inferir_test_a2.py \
  --modelo gemma3:1b \
  --corrida 1 \
  --preflight
```

Ejecutar:

```bash
python3 src/inferir_test_a2.py \
  --modelo gemma3:1b \
  --corrida 1

python3 src/inferir_test_a2.py \
  --modelo gemma3:1b \
  --corrida 2

python3 src/inferir_test_a2.py \
  --modelo gemma3:1b \
  --corrida 3
```

Entre corridas:

```bash
ollama stop gemma3:1b
```

Los resultados LLM se almacenan en:

```text
results/llm_test/
```

### 8.5. Auditoría de corridas

Una vez completadas las seis corridas LLM:

```bash
python3 src/auditar_corridas_test_a2.py
```

La auditoría verifica:

- Cantidad de eventos.
- Identificadores únicos.
- Integridad de hashes.
- Coherencia de configuraciones.
- Respuestas inválidas.
- Contadores de tokens.
- Variabilidad entre corridas.

### 8.6. Ejecución del clasificador regex

Primero:

```bash
python3 src/inferir_regex_test_a2.py \
  --corrida 1 \
  --preflight
```

Ejecutar las tres corridas:

```bash
python3 src/inferir_regex_test_a2.py --corrida 1
python3 src/inferir_regex_test_a2.py --corrida 2
python3 src/inferir_regex_test_a2.py --corrida 3
```

Los resultados se almacenan en:

```text
results/regex_test/
```

### 8.7. Análisis final

Calcular métricas de clasificación:

```bash
python3 src/analizar_test_a2.py
```

Analizar los errores:

```bash
python3 src/analizar_errores_a2.py
```

Seleccionar casos representativos:

```bash
python3 src/seleccionar_errores_a2.py
```

Los resultados finales se almacenan principalmente en:

```text
results/analisis_final/
```

La inferencia y el análisis de métricas se realizan por separado. Las etiquetas de test se utilizan en la evaluación posterior, no en la construcción de los prompts de inferencia.

---

## 9. Resultados experimentales

Se realizaron tres corridas por clasificador sobre los 361 eventos de test.

En total:

```text
Regex: 1083 clasificaciones
Qwen3: 1083 clasificaciones
Gemma: 1083 clasificaciones

Total: 3249 clasificaciones
```

### 9.1. Clasificación binaria

| Clasificador | Precisión | Recall | F1 |
|---|---:|---:|---:|
| Regex multiclase | 1,0000 | 0,7273 | **0,8421** |
| Qwen3 0.6B | 0,4964 | 0,8831 | 0,6355 |
| Gemma 3 1B | 0,2219 | 1,0000 | 0,3632 |

### 9.2. Clasificación multiclase

| Clasificador | Macro-F1 |
|---|---:|
| Regex multiclase | **0,8353** |
| Qwen3 0.6B | 0,4715 |
| Gemma 3 1B | 0,1198 |

El macro-F1 se calcula sobre las clases presentes: INFO, MEDIO y ALTO.

### 9.3. Falsos positivos y falsos negativos

| Clasificador | TP | TN | FP | FN |
|---|---:|---:|---:|---:|
| Regex | 56 | 284 | 0 | 21 |
| Qwen3 | 68 | 215 | 69 | 9 |
| Gemma | 77 | 14 | 270 | 0 |

Regex obtuvo el mayor F1 y no generó falsos positivos en el conjunto experimental.

Qwen3 detectó más amenazas que regex, pero aumentó la cantidad de falsas alarmas.

Gemma detectó todas las amenazas, aunque clasificó incorrectamente gran parte de la actividad legítima.

### 9.4. Rendimiento computacional

| Clasificador | Latencia media | RAM pico registrada |
|---|---:|---:|
| Regex | 0,01888 ms | 18,50 MiB |
| Qwen3 | 8,5811 s | 1103,95 MiB |
| Gemma | 5,0924 s | 1067,56 MiB |

La memoria de regex corresponde al pico RSS del proceso Python.

Para los LLM se utilizó la suma del RSS de los procesos `ollama` y `llama-server`.

La primera corrida de Qwen3 tuvo una medición parcial de RAM y no se incluyó en el promedio comparable.

### 9.5. Repetibilidad

Las tres corridas de cada clasificador produjeron las mismas decisiones sobre los campos:

```text
amenaza
nivel
tipo
```

La concordancia entre corridas fue del 100 % y la desviación del F1 fue cero.

Estos resultados corresponden al entorno y configuración utilizados.

---

## 10. Limitaciones del experimento

Los resultados deben interpretarse considerando las siguientes limitaciones:

- Los escenarios fueron generados en un entorno controlado.
- No representan necesariamente ataques reales en producción.
- La normalización eliminó parte de los argumentos y del contexto original.
- El 91,14 % de los eventos de test compartía texto normalizado con desarrollo.
- No se incluyeron eventos reales con severidad BAJO.
- Los 32 eventos de test con texto no visto en desarrollo eran legítimos.
- Los modelos utilizados fueron variantes pequeñas ejecutadas exclusivamente mediante CPU.
- La validación JSON no garantiza la calidad de las explicaciones generadas.

Se identificaron 87 patrones normalizados diferentes en el dataset, sin conflictos de etiquetas entre textos idénticos.

Sin embargo, la ausencia de conflictos no demuestra que los registros contengan toda la información necesaria para justificar cada clasificación.

---

## 11. Trabajo futuro

Como principal propuesta de mejora se plantea desarrollar un **clasificador híbrido**.

El sistema podría combinar:

1. Reglas deterministas para detectar indicadores explícitos.
2. Análisis mediante modelos de lenguaje para eventos ambiguos o no cubiertos por las reglas.
3. Controles adicionales para reducir falsos positivos.

También se propone:

- Enriquecer los registros normalizados con argumentos de `EXECVE` y datos de `PROCTITLE`.
- Incorporar escenarios adicionales de seguridad.
- Añadir eventos de severidad BAJO.
- Utilizar nuevos conjuntos de prueba con patrones independientes.
- Evaluar modelos más grandes o especializados.
- Incorporar métricas para evaluar la calidad de las explicaciones.
- Medir el costo operativo de revisar alertas incorrectas.

El objetivo de estas mejoras sería aumentar la capacidad de detección sin incrementar excesivamente las falsas alarmas ni el costo computacional.

---

## 12. Seguridad y reproducibilidad

Para reproducir el trabajo se recomienda:

- Utilizar una máquina virtual aislada.
- No ejecutar escenarios de seguridad sobre sistemas de producción.
- No publicar registros sensibles sin revisarlos.
- Conservar los archivos originales y las etiquetas de referencia.
- Mantener la configuración experimental congelada.
- Registrar versiones y hashes de los modelos.
- Evitar modificar los prompts o clasificadores después de evaluar test.

El protocolo experimental se encuentra documentado en:

```text
docs/protocolo_test_a2.json
```

Los criterios de severidad se encuentran en:

```text
docs/criterios_severidad.md
```

Los archivos originales y resultados completos pueden estar excluidos de Git, por lo que es necesario disponer de ellos para reproducir exactamente las métricas históricas.

---

## 13. Estado del proyecto

**Estado: implementación y evaluación experimental completadas.**

Se finalizaron:

- Recolección y procesamiento de eventos auditd.
- Generación de escenarios controlados.
- Preparación y etiquetado del dataset.
- Implementación del clasificador regex.
- Integración de Qwen3 y Gemma con Ollama.
- Evaluación y selección de prompts.
- Congelamiento del protocolo experimental.
- Tres corridas de test por clasificador.
- Análisis de métricas binarias y multiclase.
- Evaluación de rendimiento y memoria.
- Auditoría de repetibilidad.
- Análisis de errores representativos.

La metodología completa, las evidencias y la discusión crítica de los resultados se encuentran documentadas en el informe final del TP.

