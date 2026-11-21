# SPEC v0 — gta6-clipping-agent

Versión: v0 · Fecha: 2026-11-17 · Revisada con D5, D12 y D15 (ver docs/DECISIONS.md)

## 1. Contexto

Clips de GTA 6 de streamers en español o en inglés, sacados de VODs. Un VOD es
la grabación de un directo ya terminado.

## 2. Objetivo

Datos de un VOD → los 5 mejores momentos para clipear, como una lista JSON que
revisa un humano. El sistema no edita vídeo ni publica nada.

## 3. Flujo v0

```
ficheros locales (transcripción, chat)
  → cargadores                           (fase 1)  → segments, chat_events
  → generador de candidatos, sin IA      (fase 2)  → hasta 20 candidatos con reaccion_chat
  → juez LLM tras una interfaz           (fase 3)  → momentos puntuados y validados
  → orden por puntuación, top 5          (fase 3)
  → CLI → resultados.json                (fase 4)
```

El detector (fases 2 y 3) es agnóstico a la fuente: recibe trozos
normalizados, nunca una URL ni una ruta de fichero.

## 4. Entrada al núcleo (interfaces internas)

Todos los tiempos van en segundos desde el inicio del directo.

| Interfaz      | Forma                          | Qué es                         |
|---------------|--------------------------------|--------------------------------|
| `segments`    | `[{start_s, end_s, text}]`     | transcripción por trozos       |
| `chat_events` | `[{t_s, message}]`             | mensajes de chat con timestamp |

### 4.1 Ficheros de origen (fase 1)

Los ficheros de origen, en JSON o CSV, se convierten a las interfaces internas
en los cargadores de la fase 1. Sus claves canónicas son las de las
interfaces:

- Transcripción: `start_s`, `end_s`, `text`.
- Chat: `t_s`, `message`.

Los tiempos se aceptan como número en segundos o como texto `"HH:MM:SS"`. El
cargador los normaliza siempre a segundos.

Si un fichero trae otras claves, el cargador falla con un error que dice qué
claves esperaba.

## 5. Salida

JSON: una lista de momentos ordenada de mayor a menor `puntuacion`, con 5
momentos como máximo.

```json
[
  {
    "inicio": "01:23:45",
    "fin": "01:24:30",
    "puntuacion": 87,
    "desglose": {
      "reaccion_chat": 28,
      "contexto": 22,
      "novedad": 20,
      "gancho": 17
    },
    "categoria": "bug gracioso",
    "gancho": "Texto propuesto para el gancho del clip",
    "chat": {
      "msg_min": 142.0,
      "multiplicador": 4.7
    }
  }
]
```

| Campo                     | Regla                                                               |
|---------------------------|---------------------------------------------------------------------|
| `inicio`, `fin`           | formato `HH:MM:SS`, `inicio` < `fin`, dentro de la ventana candidata |
| `puntuacion`              | entero 0-100, igual a la suma de `desglose`                         |
| `desglose.reaccion_chat`  | 0-30, calculado por código (sección 7.1)                            |
| `desglose.contexto`       | 0-25, lo juzga el LLM juez                                          |
| `desglose.novedad`        | 0-25, lo juzga el LLM juez                                          |
| `desglose.gancho`         | 0-20, lo juzga el LLM juez                                          |
| `categoria`               | una de la lista cerrada (sección 6)                                 |
| `gancho`                  | gancho propuesto, en el idioma dominante de la transcripción        |
| `chat.msg_min`            | mensajes por minuto en la ventana del pico                          |
| `chat.multiplicador`      | `msg_min` / línea base del VOD                                      |

## 6. Categorías (lista cerrada)

`"reaccion"`, `"bug gracioso"`, `"secreto"`, `"momento WTF"`, `"jugada"`,
`"muerte absurda"`, `"otro"`.

Cualquier otro valor no valida.

## 7. Rúbrica (100 puntos)

| Criterio                      | Puntos | Quién lo mide           |
|-------------------------------|--------|-------------------------|
| Reacción de viewers           | 0-30   | código (conteo de chat) |
| Se entiende sin contexto      | 0-25   | LLM juez                |
| Novedad de GTA 6              | 0-25   | LLM juez                |
| Fuerza del gancho             | 0-20   | LLM juez                |

### 7.1 Reacción de viewers (0-30): la mide el código

La mide el código contando mensajes del chat. El LLM nunca la estima.

- El chat se cuenta por segundo. La reacción se mide con una ventana deslizante
  de 60 segundos que avanza de 1 en 1 segundo (D15). Cada ventana se expresa en
  mensajes por minuto.
- Línea base = mediana de mensajes/minuto de todas las ventanas deslizantes
  completas del VOD (D15).
  - Si la mediana es 0, la línea base pasa a ser la media de esas ventanas.
  - Si la media también es 0, el sistema falla con el error explícito "chat
    sin actividad suficiente". No se inventan puntuaciones.
- Multiplicador de una ventana = mensajes/minuto de la ventana / línea base.
  Los mensajes/minuto del candidato (`chat.msg_min`) se redondean a entero con
  half-up; el multiplicador no se redondea.
- Puntos según el multiplicador, con interpolación lineal dentro de cada
  tramo:

| Multiplicador   | Puntos                         |
|-----------------|--------------------------------|
| < x1.0          | 0                              |
| x1.0 – x1.5     | 0 → 10                         |
| x1.5 – x2.5     | 11 → 20                        |
| x2.5 – x4       | 21 → 27                        |
| x4 – x6         | 28 → 30                        |
| ≥ x6            | 30 (satura)                    |

Ejemplo: x2.0 está a la mitad del tramo x1.5 – x2.5, así que da la mitad de
11-20: 15,5 puntos. En el tramo alto, x4 = 28 y x6 o más = 30.

Los puntos de reacción (`reaction_points`) son decimales y se convierten a
entero con redondeo half-up al construir el `Moment` en la fase 3 (15,5 → 16),
porque `reaccion_chat` es entero (D11).

**Corrección del retraso del chat.** El pico de chat llega 5-20 s DESPUÉS del
momento. El pico es una ventana de 60 s, y la ventana candidata se mide desde
sus extremos:

```
ventana candidata = [inicio del pico − 60 s, fin del pico + 15 s]
```

Los 15 s se cuentan después del fin de la ventana de 60 s del pico, no después
de su inicio. El inicio se recorta a 0 al principio del VOD. El final no se
recorta al final del VOD, porque el detector no conoce su duración (D11).

**Selección de candidatos (D15).** Se toman hasta 20 inicios de ventana
(top-K), ordenados por número de mensajes, con supresión de no-máximos: un
inicio se descarta si queda a menos de 120 s de otro ya elegido (a exactamente
120 s se permite). A igualdad de mensajes gana el inicio menor. Si varias
ventanas seguidas tienen la misma suma, el inicio del pico es la primera de
esa meseta: es el primero que se elige, y una meseta más larga que la separación
puede dar otros inicios a 120 s o más de él. Las ventanas sin ningún mensaje no
se emiten.

No hay umbral mínimo de multiplicador ni relleno: un VOD con poca reacción da
candidatos con pocos puntos, y la rúbrica del juez (sección 7.2) decide si el
momento vale. Con un chat con actividad siempre hay candidatos, hasta 20. Un
chat más corto que la ventana se mide con una única ventana que cubre todo el
chat. El único fallo es el chat sin actividad suficiente, descrito arriba.

Dos candidatos vecinos pueden solaparse hasta 15 s, porque sus ventanas de 135 s
distan 120 s entre inicios. No se fusionan. La desduplicación de momentos que
hace el juez tras puntuar (`_deduplicate` en `src/judge.py`, de la fase 3; ver
la [nota de la fase 3](docs/sessions/2026-11-19-fase-3.md)) es la red final
contra duplicados.

Los candidatos salen ordenados por puntos de `reaccion_chat` de mayor a menor y,
a igualdad, por inicio ascendente.

### 7.2 Criterios que juzga el LLM juez

- **Se entiende sin contexto (0-25):** el momento se entiende sin haber visto
  el resto del directo.
- **Novedad de GTA 6 (0-25):** cuánto muestra de nuevo sobre GTA 6.
- **Fuerza del gancho (0-20):** cuánto engancha el momento y el gancho
  propuesto.

## 8. Juez (LLM)

- El juez va tras una interfaz `Judge`: `judge(candidate, segments)`
  devuelve un `Judgment`. El primer proveedor es la API de Gemini en tier
  gratuito; otro proveedor se añade sin tocar el resto (D12).
- Recibe SOLO los candidatos de la fase 2, cada uno con su trozo de
  transcripción. Nunca recibe el VOD entero.
- Ajusta `inicio`/`fin` fino dentro de la ventana candidata. No puede
  devolver timestamps fuera de ella.
- Puntúa contexto, novedad y gancho según la rúbrica, asigna una categoría de
  la lista cerrada y escribe el gancho en el idioma dominante de la
  transcripción (español o inglés).
- Su salida es estructurada y se valida con pydantic contra el esquema de la
  sección 5.
- Si la salida no valida (o trae tiempos fuera de la ventana, o falla la
  llamada), se repite la llamada una vez. Si vuelve a fallar, se registra el
  fallo y se sigue con el resto de candidatos.
- Puntuación total = `reaccion_chat` (ya calculada por código) + las tres
  puntuaciones del juez. Se ordena de mayor a menor.
- En cada ejecución registra cuántas llamadas a la API se hicieron y los
  tokens usados.
- Tests con la API mockeada: ningún test llama a la API real.

## 9. CLI (fase 4)

```bash
python -m src.main --transcript <fichero> --chat <fichero> --out resultados.json [--reference <fichero>]
```

`--reference` es opcional: si se pasa, el CLI evalúa los momentos propuestos
contra los clips de referencia de la sección 10.

### 9.1 Arnés de evaluación sin juez (fase 5)

```bash
python -m src.harness --chat <fichero> --reference <fichero> [--window-s 60] [--k 20] [--trials 2000] [--seed 0]
```

Mide los candidatos del detector, no los momentos del juez, y no usa juez ni
red. Para K = 5, 10, 20 y 40 informa de cuántos clips de referencia solapa algún
candidato, con la tolerancia de la sección 10 (±60 s, extremos incluidos). Si
`--k` no está en esa lista, se informa también de su fila. Lo compara con la
media de un azar de `--trials` pruebas con la semilla `--seed` y da un
p-valor por permutación. El azar sortea los inicios de ventana con la misma
separación mínima que el detector (120 s), así que compara con la misma
selección que se mide. El veredicto (D15) es PASS si aciertos@K para `--k` (20
por defecto) supera al azar con p<0,05 y el detector da candidatos; si no, FAIL.
Un FAIL sale también con código 0: el veredicto va en la salida, no en el código
de salida.

Códigos de salida: 0 si corre, 1 si un fichero no existe o no es válido, o el
chat no tiene actividad suficiente, 2 si los argumentos o la configuración son
inválidos, 130 si se interrumpe.

**Dos medidas distintas.** El `--reference` del CLI evalúa los momentos que salen
del juez, como mucho 5. El arnés evalúa los candidatos, hasta 20. Aciertos@20 del
arnés y la evaluación del CLI no son la misma cifra.

## 10. Criterios de aceptación del v0

- Procesa un VOD real de 2-3 h sin romperse por longitud.
- Evaluación (fase 4): los 5 momentos se comparan contra los 10 clips más
  vistos de Twitch de ese mismo VOD. Esa referencia se aporta a mano en un
  JSON (o CSV) con los tiempos de cada clip. Acierto = solape de ±60 s.

## 11. Fuera de alcance en v0

- Modo en directo: previsto para v3, sobre el mismo detector.
- Edición de vídeo: v1.
- Automatizar la obtención de los clips de referencia de Twitch: en v0 se
  aportan a mano.
- Publicación de cualquier tipo: permanentemente fuera. La subida es manual.

## 12. Preguntas abiertas

Las demás preguntas quedaron resueltas en D5 (docs/DECISIONS.md) y se
incorporaron a las secciones 4 y 7.1. Queda solo:

6. **Fase 4:** cuántos clips de Twitch se usan como referencia en la
   evaluación y cómo se consiguen. **Resuelta para fase 4, método manual:**
   10 clips más vistos, aportados a mano en un JSON (sección 10).
