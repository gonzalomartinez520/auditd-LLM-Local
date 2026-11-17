
# TP Final A2 — Criterios de clasificación

## 1. Objetivo

Establecer criterios previos para clasificar eventos de
auditoría de Linux según su nivel de severidad.

La clasificación se realizará sobre eventos completos,
agrupados por identificador de auditoría.

Los niveles disponibles son:

- INFO
- BAJO
- MEDIO
- ALTO

Estos criterios deben permanecer definidos antes de
evaluar los clasificadores sobre el conjunto de prueba.

## 2. Definiciones de severidad

### INFO

Actividad normal, administrativa o autorizada,
sin evidencia concreta de comportamiento sospechoso.

Ejemplos:
- Consultas administrativas habituales.
- Mantenimiento del sistema.
- Accesos autorizados a información del sistema.
- Ejecuciones sin indicadores de amenaza.

### BAJO

Actividad inusual o potencialmente sensible que
merece revisión, pero sin evidencia suficiente para
considerarla una amenaza de severidad media o alta.

Ejemplos:
- Comportamientos atípicos de bajo impacto.
- Operaciones sensibles cuyo contexto no permite
  establecer claramente una intención maliciosa.

La presencia de un archivo sensible no determina
automáticamente este nivel.

### MEDIO

Indicadores concretos de comportamiento sospechoso
relacionado con autenticación, privilegios o
reconocimiento del sistema, sin evidencia suficiente
de compromiso consumado.

Ejemplos:
- Intentos fallidos de autenticación relevantes.
- Reconocimiento de privilegios.
- Combinaciones anómalas de UID y EUID.

### ALTO

Actividad que representa un riesgo elevado para
la seguridad del sistema, como intentos de acceso
directo a credenciales o modificaciones peligrosas
de configuraciones críticas.

Ejemplos:
- Lecturas no justificadas de archivos de credenciales.
- Modificaciones peligrosas de políticas de privilegios.

La etiqueta ALTO no implica necesariamente que
el ataque haya tenido éxito.

## 3. Relación entre amenaza y nivel

La clasificación binaria y la severidad se relacionan
de la siguiente manera:

INFO  -> amenaza = false
BAJO  -> amenaza = true
MEDIO -> amenaza = true
ALTO  -> amenaza = true

Esta relación constituye una convención operativa
del experimento.

## 4. Tipos de evento

Se utilizará el siguiente vocabulario:

- actividad_normal
- autenticacion
- reconocimiento
- anomalia_privilegios
- acceso_sensible
- modificacion_configuracion
- anomalia_operativa
- otro

El tipo identifica la naturaleza del evento.
El nivel representa su severidad.

No son conceptos equivalentes.

## 5. Criterios metodológicos

1. La severidad de referencia se asignará antes
   de ejecutar los clasificadores de cuatro niveles.

2. Las etiquetas no se obtendrán de las predicciones
   del regex ni de los LLM.

3. Se distinguirán las acciones realmente observadas
   de las simulaciones controladas.

4. No se afirmará que existió una escalada real de
   privilegios cuando solamente se simuló.

5. La falta de evidencia no se transformará
   automáticamente en evidencia de normalidad.

6. Se mantendrá la trazabilidad entre cada etiqueta
   y su evento original.

7. Los clasificadores recibirán los registros
   normalizados, pero nunca las etiquetas reales
   ni el identificador del escenario experimental.

8. Las etiquetas de test quedarán reservadas
   exclusivamente para la evaluación final.

## 6. Limitaciones

Los registros de auditd no contienen necesariamente
el contenido de los archivos modificados ni la
intención del usuario.

Algunos escenarios pueden ser indistinguibles
a partir de los campos normalizados disponibles.

Las etiquetas experimentales representan el escenario
controlado de referencia; no siempre constituyen una
conclusión demostrable a partir del registro aislado.

No se crearán artificialmente eventos de un nivel
de severidad para equilibrar las clases.


## 7. Tratamiento de anomalías operativas

Se identificaron dos eventos ANOM_ABEND de systemd-logind:

- 1794002138.650:1055
- 1794005005.558:2042

Los registros de auditd muestran una terminación con
señal SIGABRT (sig=6).

La revisión de journalctl del 6 de noviembre de 2026
confirmó que ambos procesos fueron terminados por
systemd después de un timeout del watchdog.

Los servicios fueron reiniciados posteriormente.

Se establece para ambos eventos:

- amenaza: false
- nivel: INFO
- tipo: anomalia_operativa

Justificación: los registros muestran fallos operativos,
pero no aportan evidencia concreta de un ataque.

Esta decisión no implica que los fallos carezcan de
impacto operativo.

## 8. Distribución de severidad de referencia

La distribución establecida para los 519 eventos es:

- INFO: 409
- BAJO: 0
- MEDIO: 90
- ALTO: 20

El nivel BAJO se conserva en la taxonomía, pero no tiene
ejemplos de referencia en este dataset.

Esta ausencia limita la evaluación multiclase y deberá
documentarse al interpretar la matriz de confusión
y las métricas por nivel.

## 9. Congelamiento de criterios

Estas definiciones y las etiquetas de referencia se
establecen antes de evaluar clasificadores multiclase.

No se modificarán a partir de las predicciones obtenidas
sobre el conjunto de prueba.

Las etiquetas de referencia no forman parte de las
entradas enviadas a los clasificadores.

