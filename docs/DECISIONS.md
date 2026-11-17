# Decisiones

Cada decisión lleva fecha, qué se decide, por qué y qué implica. Las
propuestas que salen del alcance de la SPEC se registran abajo, en
"Propuestas", antes de implementarse, con estado `pendiente`, `aceptada` o
`rechazada`.

## D1 · 2026-11-17 · VOD primero; modo en directo en v3 reutilizando el detector

- **Decisión:** el v0 trabaja con VODs (directos ya terminados). El modo en
  directo llega en v3 y reutiliza el mismo detector.
- **Por qué:** un VOD da datos completos y repetibles, y se puede evaluar
  contra los clips que ya creó la audiencia en Twitch.
- **Implica:** el detector es agnóstico a la fuente. Recibe trozos
  normalizados (`segments`, `chat_events`), nunca una URL ni una ruta de
  fichero, así que en v3 solo cambia la ingesta.

## D2 · 2026-11-17 · Sin frameworks de agentes en v0

- **Decisión:** nada de LangChain, LangGraph ni similares. El orquestador es
  simple y explícito, escrito por nosotros con el SDK oficial de Anthropic.
- **Por qué:** es un proyecto de aprendizaje y cada pieza tiene que
  entenderse.
- **Implica:** las llamadas, los reintentos, la validación y el registro de
  tokens se escriben a mano.

## D3 · 2026-11-17 · La reacción la mide código determinista; Claude solo juzga

- **Decisión:** `reaccion_chat` (0-30) se calcula contando mensajes del chat.
  Claude solo puntúa contexto, novedad y gancho.
- **Por qué:** contar mensajes es exacto, barato y reproducible; un LLM lo
  estimaría peor.
- **Implica:** el generador de candidatos (fase 2) no usa IA, y el juez
  (fase 3) recibe `reaccion_chat` ya calculada y no la modifica.

## D4 · 2026-11-17 · Nunca autopublicar; aprobación humana siempre

- **Decisión:** el sistema nunca sube ni publica nada en ninguna plataforma.
- **Por qué:** cada clip lo revisa y lo sube a mano una persona.
- **Implica:** no existe código de subida ni se propone. El flujo termina en
  una lista JSON de momentos propuestos. Es una restricción permanente, no
  solo del v0.

## Propuestas

Ninguna por ahora.
