# SPEC v0 — gta6-clipping-agent

Versión: v0 · Fecha: 2026-11-17

## 1. Contexto

Clips de GTA 6 de streamers en español, sacados de VODs. Un VOD es la
grabación de un directo ya terminado.

## 2. Objetivo

Datos de un VOD → los 5 mejores momentos para clipear, como una lista JSON que
revisa un humano. El sistema no edita vídeo ni publica nada.

## 3. Flujo v0

```
ficheros locales (transcripción, chat)
  → cargadores                           (fase 1)  → segments, chat_events
  → generador de candidatos, sin IA      (fase 2)  → 15-20 candidatos con reaccion_chat
  → juez con la API de Claude            (fase 3)  → momentos puntuados y validados
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

Los ficheros de origen (transcripción y chat en JSON/CSV) se convierten a
estas interfaces en los cargadores de la fase 1.

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
| `desglose.contexto`       | 0-25, lo juzga Claude                                               |
| `desglose.novedad`        | 0-25, lo juzga Claude                                               |
| `desglose.gancho`         | 0-20, lo juzga Claude                                               |
| `categoria`               | una de la lista cerrada (sección 6)                                 |
| `gancho`                  | texto propuesto para el gancho del clip                             |
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
| Se entiende sin contexto      | 0-25   | Claude                  |
| Novedad de GTA 6              | 0-25   | Claude                  |
| Fuerza del gancho             | 0-20   | Claude                  |

### 7.1 Reacción de viewers (0-30): la mide el código

La mide el código contando mensajes del chat. El LLM nunca la estima.

- Ventanas de 60 segundos.
- Línea base = mediana de mensajes/minuto de todo el VOD.
- Multiplicador de una ventana = mensajes/minuto de la ventana / línea base.
- Puntos según el multiplicador:

| Multiplicador   | Puntos |
|-----------------|--------|
| ≤ x1.5          | 0-10   |
| x1.5 – x2.5     | 11-20  |
| x2.5 – x4       | 21-27  |
| > x4            | 28-30  |

**Corrección del retraso del chat.** El pico de chat llega 5-20 s DESPUÉS del
momento. La ventana candidata va desde 60 s antes del inicio del pico hasta
15 s después.

**Selección de candidatos.** Se fusionan los picos cercanos y se quedan los
15-20 mejores, cada uno con sus puntos de `reaccion_chat` ya calculados.

### 7.2 Criterios que juzga Claude

- **Se entiende sin contexto (0-25):** el momento se entiende sin haber visto
  el resto del directo.
- **Novedad de GTA 6 (0-25):** cuánto muestra de nuevo sobre GTA 6.
- **Fuerza del gancho (0-20):** cuánto engancha el momento y el gancho
  propuesto.

## 8. Juez (Claude)

- Recibe SOLO los candidatos de la fase 2, cada uno con su trozo de
  transcripción. Nunca recibe el VOD entero.
- Ajusta `inicio`/`fin` fino dentro de la ventana candidata. No puede
  devolver timestamps fuera de ella.
- Puntúa contexto, novedad y gancho según la rúbrica, asigna una categoría de
  la lista cerrada y escribe el gancho.
- Su salida es estructurada y se valida con pydantic contra el esquema de la
  sección 5.
- Si la salida no valida, reintenta una vez pasándole el error. Si vuelve a
  fallar, registra el fallo y sigue con el resto de candidatos.
- Puntuación total = `reaccion_chat` (ya calculada por código) + las tres
  puntuaciones del juez. Se ordena de mayor a menor.
- En cada ejecución registra cuántas llamadas a la API se hicieron y los
  tokens usados.
- Tests con la API mockeada: ningún test llama a la API real.

## 9. CLI (fase 4)

```bash
python -m src.main --transcript <fichero> --chat <fichero> --out resultados.json
```

## 10. Criterios de aceptación del v0

- Procesa un VOD real de 2-3 h sin romperse por longitud.
- Evaluación: los 5 momentos se comparan contra los clips más creados por la
  audiencia de ese mismo VOD en Twitch. Acierto = solape de ±60 s.

## 11. Fuera de alcance en v0

- Modo en directo: previsto para v3, sobre el mismo detector.
- Edición de vídeo: v1.
- Publicación de cualquier tipo: permanentemente fuera. La subida es manual.

## 12. Preguntas abiertas

Puntos que la spec no fija. Se resuelven antes de la fase indicada y la
respuesta se registra en docs/DECISIONS.md.

1. **Fase 1:** columnas y claves exactas de los ficheros JSON/CSV de
   transcripción y chat.
2. **Fase 2:** cómo se reparten los puntos dentro de cada tramo de reacción
   (por ejemplo, interpolación lineal según el multiplicador).
3. **Fase 2:** "hasta 15 s después": ¿del inicio del pico o del final del pico?
4. **Fase 2:** qué distancia cuenta como "picos cercanos" para fusionarlos.
5. **Fase 2:** qué hacer si la mediana de mensajes/minuto es 0 (chat muy
   tranquilo), porque el multiplicador dividiría entre 0.
6. **Fase 4:** cuántos clips de Twitch se usan como referencia en la
   evaluación y cómo se consiguen.
