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

## D5 · 2026-11-17 · Resolución de las preguntas abiertas de la SPEC

- **Decisión:** el arquitecto resuelve las 6 preguntas abiertas que listaba la
  sección 12 de la SPEC:
  1. **Formatos de entrada (fase 1).** Las claves canónicas son las de las
     interfaces: transcripción JSON/CSV con `start_s, end_s, text` y chat con
     `t_s, message`. Los tiempos se aceptan como número en segundos o como
     texto `"HH:MM:SS"`, y el cargador los normaliza a segundos. Si un fichero
     trae otras claves, el cargador falla con un error que dice qué esperaba.
  2. **Puntos dentro de cada tramo.** Interpolación lineal. Por ejemplo, x2,0
     está a la mitad del tramo x1,5-x2,5, así que da la mitad de 11-20: 15-16
     puntos. En el tramo alto satura: x4 = 28 y x6 o más = 30. Por debajo de
     x1,0 = 0.
  3. **"Hasta 15 s después".** Cuenta desde el fin de la ventana de 60 s del
     pico, no desde su inicio. Ventana candidata =
     `[inicio del pico − 60 s, fin del pico + 15 s]`.
  4. **Picos cercanos.** Si dos ventanas candidatas se solapan o quedan a menos
     de 120 s, se fusionan en una, con la unión de tiempos y los puntos del
     pico mayor.
  5. **Mediana 0.** La línea base pasa a ser la media. Si la media también es
     0, el sistema falla con el error explícito "chat sin actividad
     suficiente"; no se inventan puntuaciones.
  6. **Evaluación (fase 4, no bloquea ahora).** La referencia son los 10 clips
     más vistos de Twitch de ese VOD, aportados a mano en un JSON con sus
     tiempos. Automatizar su obtención queda fuera del v0.
- **Por qué:** las fases 1 y 2 necesitan estos criterios para implementarse sin
  decidir sobre la marcha, y las decisiones de arquitectura no se toman en el
  código.
- **Implica:** la SPEC incorpora cada resolución en su sección (4, 7.1, 10 y
  11) y la sección 12 conserva solo la pregunta 6. Los cargadores de la fase 1
  validan claves y normalizan tiempos; el generador de candidatos de la fase 2
  implementa la interpolación, la ventana, la fusión y la regla de línea base;
  la fase 4 evalúa contra un JSON manual.

## D6 · 2026-11-17 · Flujo de ramas y PRs por fase

- **Decisión:**
  - Cada fase trabaja en su propia rama, con nombre `fase-N/descripcion-corta`
    (por ejemplo, `fase-1/modelos-ingesta`).
  - Claude Code abre la PR contra `main` con `gh`.
  - La fusión la hace solo una persona, con los tests en verde.
  - Excepción: los cambios que solo tocan documentación van directos a `main`.
  - No hay protección dura de rama en GitHub por ahora.
- **Por qué:** una fase, una rama y una PR dejan cada fase revisable por
  separado, y la fusión humana mantiene la aprobación del arquitecto. La
  excepción evita abrir una PR por cada cambio de documentación.
- **Implica:** CLAUDE.md resume el flujo en "Método de trabajo". Claude Code
  nunca fusiona. Sin protección de rama, la regla se sostiene por convención.
  Además, `CHANGELOG.md` pasa a ser convención propia del proyecto: toda PR
  añade su entrada en `## [Unreleased]` antes de fusionarse.

## D7 · 2026-11-17 · Convenciones del proyecto y separación de herramientas locales

- **Decisión:**
  1. Los mensajes de commit van en inglés desde la fase 1. La documentación
     sigue en español.
  2. Ninguna regla no commiteada gobierna el proyecto. El bloque de
     convenciones que un plugin añade al `CLAUDE.md` local sale del fichero
     seguido y pasa a `CLAUDE.local.md`, que no se commitea.
  3. `.gitignore` añade `CLAUDE.local.md` y `.claude/`.
- **Por qué:** lo que gobierna el proyecto tiene que estar en el repo, donde
  cualquiera lo puede leer y revisar. Lo que añade la herramienta local de una
  persona queda fuera del historial.
- **Implica:** `CLAUDE.md` es la única fuente commiteada de reglas
  (restricciones duras, método de trabajo, flujo de ramas y CHANGELOG de D6).
  `CLAUDE.local.md` es un ajuste personal y no obliga al proyecto. La
  estructura descrita en `CLAUDE.md` incorpora `requirements.txt`, que llega en
  la fase 1 con `pydantic` y `pytest` solamente.

## D8 · 2026-11-17 · CI desde la fase 1; CD fuera hasta v2

- **Decisión:**
  - Hay CI en GitHub Actions desde la fase 1. En pull requests y en pushes a
    `main` ejecuta, sobre Python 3.11: `pip install -r requirements.txt`,
    `ruff check .`, `black --check .` y `python -m pytest`.
  - No hay CD hasta v2, donde irán Docker y GHCR.
  - El CI no usa ningún secreto: los tests no llaman a la API real.
- **Por qué:** D6 pide fusionar solo con tests en verde, y el CI hace esa
  condición comprobable por quien revisa la PR sin depender de que se hayan
  pasado en local. No hay nada que desplegar hasta v2.
- **Implica:** `ruff` y `black` entran en `requirements.txt` junto a
  `pydantic` y `pytest`, con su configuración por defecto. El workflow vive en
  `.github/workflows/ci.yml`.

## D10 · 2026-11-17 · Umbral de candidato x1,5 y tope de 20 candidatos

- **Decisión:**
  - Un minuto del chat genera candidato solo si su multiplicador es mayor o
    igual que x1,5.
  - El generador devuelve como máximo 20 candidatos, ordenados por puntos de
    reacción de mayor a menor y, a igualdad, por inicio ascendente.
- **Por qué:** la SPEC 7.1 pide quedarse con "los 15-20 mejores", pero no fija
  qué minuto cuenta como pico ni el número exacto. x1,5 es donde empieza el
  tramo de 11-20 puntos de la tabla: por debajo, la reacción vale como mucho
  10 de 30 puntos y no justifica gastar una llamada al juez. El tope de 20 es
  el extremo alto del rango de la SPEC y acota el coste de la fase 3.
- **Implica:** `src/peaks.py` fija `CANDIDATE_MIN_MULTIPLIER = 1.5` y
  `MAX_CANDIDATES = 20`. Un VOD con pocos picos puede dar menos de 15
  candidatos, o ninguno si el chat es uniforme; no se rellenan con minutos por
  debajo del umbral.
- **Estado:** el umbral ×1,5 queda sustituido por D15 (selección top-K); el
  tope de 20 se mantiene.

## D11 · 2026-11-17 · Dictámenes sobre la auto-revisión de la fase 2

- **Decisión:** el arquitecto resuelve los cinco puntos que dejó abiertos la
  auto-revisión de la PR de la fase 2:
  1. **Tope de 300 s por ventana candidata.** En la fusión, la ventana
     siguiente solo se une si la unión no supera 300 s. Si los supera, el
     candidato actual se cierra y esa ventana abre uno nuevo. Cada candidato
     conserva `msg_min`, multiplicador y puntos de su propio pico mayor.
  2. **Redondeo half-up de `reaction_points`** al construir el `Moment` en la
     fase 3 (15,5 → 16), porque `reaccion_chat` es entero.
  3. **Limitación aceptada:** el detector no conoce la duración del VOD. La
     línea base cuenta minutos hasta el último mensaje y el fin de una ventana
     no se recorta al final del VOD.
  4. **Pico mayor por `msg_min`;** a igualdad gana el primero.
  5. **Sin relleno** por debajo del umbral x1,5: un VOD con pocos picos da
     menos de 15 candidatos.
- **Por qué:** la fusión por distancia aplicada en cadena no acotaba la
  longitud de la ventana (diez picos a 4 minutos daban una de 38 minutos), y
  el juez de la fase 3 debe recibir trozos manejables. Los otros cuatro puntos
  fijan por escrito lo que el código ya hacía o lo que la fase 3 necesita.
- **Implica:** `src/peaks.py` fija `MAX_WINDOW_S = 300`. Una ventana sola mide
  135 s, así que bajo el tope solo se fusionan picos a 2 minutos o menos; la
  regla de los 120 s solo cambia el resultado cerca del inicio del VOD, donde
  la ventana se recorta a 0. Un grupo largo de picos seguidos se parte en
  varios candidatos que pueden solaparse en el tiempo. La fase 3 aplica el
  redondeo half-up al pasar de `Candidate` a `Moment`.
- **Estado:** el punto 5 («sin relleno») queda sustituido por D15.

## D12 · 2026-11-19 · El juez va tras una interfaz; Gemini (tier gratuito) como primer proveedor

- **Decisión:**
  1. El juez se implementa tras una interfaz `Judge`
     (`judge(candidate, segments) -> Judgment`). El pipeline depende de la
     interfaz, no de un proveedor.
  2. El primer proveedor es la API de Gemini en tier gratuito (`GeminiJudge`,
     SDK oficial `google-genai`). Es decisión de Aday no gastar en APIs.
  3. Los tests nunca llaman a la API real: el cliente del SDK se sustituye por
     un doble.
  4. Una implementación asistida por Claude Code podrá añadirse después como
     otro `Judge`, sin tocar el pipeline.
- **Por qué:** el juez es la única pieza que depende de un proveedor externo.
  Dejarlo tras una interfaz permite empezar con coste cero y cambiar de
  proveedor, o de modo de uso, sin reescribir nada más.
- **Implica:**
  - D12 supera a D2 y D3 solo en lo que toca al proveedor. "SDK oficial de
    Anthropic" (D2) y "Claude solo juzga" (D3) quedan como historia fechada: el
    juez es ahora un LLM de proveedor intercambiable. El resto de D2 y D3 sigue
    vigente, en particular que `reaccion_chat` la calcula código y el juez
    nunca la estima.
  - SPEC §3, §5, §7, §7.2 y §8, y la restricción 4 y la pila de CLAUDE.md,
    pasan a lenguaje de proveedor neutro. `.env.example` lista
    `GEMINI_API_KEY` y `GEMINI_MODEL`, sin valores; el modelo por defecto es
    `gemini-3.8-flash`.
  - La interfaz no recibe el error del intento anterior, así que el reintento
    de la SPEC §8 repite la llamada sin pasarle el error. La SPEC §8 se ajusta
    a eso.
  - Un error de la API (cuota del tier gratuito, red) cuenta como fallo del
    candidato tras el reintento, sin espera entre intentos en v0.
  - `GeminiJudge` acumula llamadas y tokens de entrada y de salida
    (`usage_metadata`) para cumplir la SPEC §8; la impresión queda para la CLI
    de la fase 4.
  - Las condiciones del tier gratuito pueden permitir a Google usar lo que se
    envía. Hoy solo se envían transcripciones de directos públicos.

## D13 · 2026-11-19 · Directos en español o en inglés

- **Decisión:** el detector sirve VODs de streamers en español o en inglés,
  no solo en español. El juez escribe el gancho en el idioma dominante de la
  transcripción (español o inglés), con 12 palabras como máximo.
- **Por qué:** el arquitecto amplía el alcance a streamers en inglés. Solo el
  juez depende del idioma: el conteo del chat de la fase 2 y los cargadores de
  la fase 1 no miran el texto.
- **Implica:**
  - El prompt de `build_prompt` habla de streamers en español o en inglés y
    pide el gancho en el idioma dominante de la transcripción. SPEC §1, §5 y
    §8, CLAUDE.md ("Qué es") y el README dejan de suponer directos solo en
    español.
  - El código no detecta el idioma: lo decide el LLM juez a partir de la
    transcripción. Otros idiomas no están previstos en v0.
  - El contrato de salida no cambia: las claves del JSON y las categorías de
    la lista cerrada (SPEC §5 y §6) siguen en español también para directos en
    inglés.

## D14 · 2026-11-19 · CLI, evaluación y datos de demostración (fase 4)

- **Decisión:**
  - `--reference` es un argumento opcional del CLI.
  - El fichero de referencia es una lista de clips con `start_s` y `end_s`
    (números o `HH:MM:SS`; las claves extra se ignoran; la maquinaria común de
    los cargadores acepta también CSV). Lo carga `load_reference` en
    `src/loaders.py` y se modela como `ReferenceClip`, de modo que
    `evaluate()` nunca recibe una ruta.
  - Un clip de referencia está detectado si algún `Moment` solapa
    `[start_s-60, end_s+60]`, extremos incluidos. Es deliberadamente distinto
    del solape estricto de la deduplicación del juez.
  - Códigos de salida: 0 correcto, 1 error fatal, 2 argumentos incorrectos
    (`argparse`), 130 interrumpido.
  - Regla del arquitecto sobre fallos de candidatos:
    - Si había candidatos y ninguno produce un momento (todos fallan en el
      juez o no tienen transcripción en su ventana), el CLI sale con 1 y no
      escribe ni sobrescribe el fichero de salida. Imprime los errores y el
      uso del juez, pero ni `Moments:`, ni la evaluación, ni la línea de
      revisión pendiente, y `main()` muestra
      `error: all N candidates failed; output not written` en stderr.
    - Cero candidatos del generador no es un error: sale con 0 y escribe `[]`.
    - Fallos parciales: sale con 0, escribe los momentos y lista los errores.
  - Un `Judge` que lanza algo distinto de `JudgeError` o `ValueError` no se
    traga: el CLI falla con traza. En v0 es lo honesto, porque indica un fallo
    del propio juez y no del candidato.
  - La ruta de salida se valida antes de cualquier llamada al juez.
  - Los datos sintéticos viven en `examples/demo/`: 90 minutos, línea base de
    12 mensajes por minuto, picos en los minutos 10, 33, 34 y 70, y una
    referencia con resultado conocido de 2/3.
  - Sin ritmo de llamadas en esta fase.
- **Por qué:** la evaluación de la SPEC §10 necesita una entrada de referencia
  sin atar el núcleo a ficheros (CLAUDE.md, restricción 2). Validar la salida
  antes de juzgar evita gastar cuota para luego no poder escribir. Los datos
  sintéticos permiten probar el flujo completo sin red y con un resultado
  conocido.
- **Implica:**
  - La SPEC §9 y §10 reflejan `--reference` y el formato JSON o CSV.
  - Un fallo en todos los candidatos (clave inválida, cuota agotada) ya no
    se confunde con "no hay momentos": sale con 1 sin tocar la salida, así una
    corrida anterior no se pierde por un fallo del proveedor.
  - La fase 4 no cierra el v0 por sí sola: el v0 se cierra cuando la corrida
    con un VOD real (SPEC §10) esté registrada en la nota de sesión.
  - Sin espera entre llamadas: la ejecución real dirá cuántos 429 aparecen en
    el tier gratuito y entonces se toma una decisión nueva.
- **Estado:** con el detector de D15 (fase 5), la demo da 20 candidatos de 135 s
  y los tres clips de su referencia caen dentro de ellos (3/3). Son medidas
  distintas: ese 3/3 mide los candidatos del detector, y la evaluación del CLI
  mide los momentos del juez (hasta 5) y depende del juez (con un juez falso que
  solo promueve los picos plantados sale 2/3). «Cero candidatos» solo ocurre si
  se sustituye el generador: con un chat con actividad, el detector siempre
  propone hasta 20.

## D15 · 2026-11-20 · Revisión del detector de picos para la fase 5

- **Decisión:**
  1. **Resolución.** El detector cuenta mensajes por segundo en un array y mide
     la reacción con una ventana deslizante de W=60 s (paso de 1 s), una sola
     escala: sin multi-escala. `msg_min` sigue siendo mensajes por minuto.
  2. **Selección.** Top-K con K=20 por puntos de reacción, con supresión de
     no-máximos (separación mínima de 120 s entre picos, la de `MERGE_GAP_S`).
     Sustituye al umbral ×1,5 de D10 y al «sin relleno» de D11.5; el tope de
     20 de D10 se mantiene. El detector nunca calla: con un chat con
     actividad devuelve siempre candidatos hasta K, aunque la reacción sea
     débil. El único caso sin candidatos es el error explícito «chat sin
     actividad suficiente» de la SPEC 7.1.
  3. **Línea base.** Mediana global por defecto, como en la SPEC 7.1. La línea
     base local o rodante no se decide con este fixture (F3) y sigue abierta
     en Propuestas.
  4. **Configuración.** `DetectorConfig` explícito (dataclass): ventana, línea
     base, K y separación mínima. Sin frameworks. La firma de
     `generate_candidates` y `Candidate`, el juez, `Moment` y la salida de la
     SPEC §5 no cambian.
  5. **Arnés de evaluación sin juez.** Mide aciertos@K contra el azar, con la
     tolerancia de D14 y un p-valor por permutación. Comparar configuraciones
     no gasta cuota del juez.
  6. **Criterio de aceptación, fijado antes de probar:** aciertos@20 sobre el
     azar con p<0,05 y nunca silencio (punto 2). Se aplica a la configuración
     fijada aquí (W=60, línea base global, K=20), no a la mejor de un barrido.
- **Hallazgos** (medidos sobre el fixture de Rubius, `~/rubius-run`, sin tocar
  el repo. Son 10 clips de una sola VOD y unas 20 configuraciones probadas sin
  corregir por comparaciones múltiples: orientativos, no una prueba):
  - **F1 · Chat capado a 15 msg/s.** En `chat.json` hay 11.223 de 30.874
    segundos (36,4 %) con exactamente 15 mensajes y ninguno con más. El origen
    no es atribuible: puede ser un límite de Twitch o de la herramienta de
    descarga, y el chat crudo se borró en la limpieza del v0. Los picos reales
    quedan aplastados; un cubo de 1 s no sirve (los timestamps son enteros) y
    desde 5 s casi no hay ventanas saturadas. Hay que comprobar el histograma
    de mensajes por segundo en cada VOD nuevo.
  - **F2 · Causa de los 0 candidatos.** Fue el umbral absoluto. Ordenando sin
    umbral, la ventana deslizante de 60 s acierta 3/5, 4/10, 5/20 y 7/40
    clips (azar: 0,4, 0,9, 1,7 y 3,1) y los cubos alineados del v0, 1/5, 2/10,
    4/20 y 4/40 (p=0,10 en K=20). Con n=10 no se distingue W=30 de W=60.
  - **F3 · La referencia está contaminada por fase.** 8 de los 10 clips caen en
    las primeras 3 h (el 35 % del VOD) y 16 de los 20 mejores picos de
    volumen también. Normalizada por su propia hora, la reacción en los clips
    vale ×0,91–1,15 frente a un p99 del VOD de ×1,30. Los aciertos de la
    línea base global miden en parte «el directo está lleno»; la local con
    suelo da 0-1 aciertos porque quita justo ese efecto. Este fixture no
    decide entre una y otra.
  - **F5 · Sin desfase calibrable.** La mejor ventana de volumen cerca de cada
    clip cae entre −144 s y +119 s de su inicio, sin sesgo. Los clips de
    referencia marcan la ventana del espectador, no el momento.
- **Por qué:** el v0 solo falló por la regla de selección, no por la señal en
  bruto. Un top-K con supresión de no-máximos da candidatos al juez en
  cualquier chat y deja que la rúbrica (SPEC §7.1) puntúe honestamente una
  reacción débil. Con 10 clips de una VOD, el criterio se fija antes de
  probar para no ajustar el detector a la referencia, y el arnés sin juez
  permite comparar sin gastar cuota.
- **Implica:**
  - `LEAD_S` y `TAIL_S` no cambian (F5).
  - Hasta 20 llamadas al juez por VOD también en chats planos.
    `chat.multiplicador` sigue mostrando la reacción real al revisor humano.
  - La fase 5 actualiza SPEC §7.1 y los tests, incluidas las expectativas de
    `examples/demo` y de `tests/test_main.py`. Si la supresión de no-máximos
    deja sin efecto la fusión de ventanas (D11.1), la PR lo explica y lo
    plantea al arquitecto.
  - La corrida de cierre de la fase 5 sobre el mismo fixture, sin descargar
    nada, es también la primera con el juez real: contrato con Gemini, 429 y
    acierto.
  - Va en su rama `fase-5/...` y su PR (D6), con Opus, cuando D15 esté en
    `main`.

## Propuestas

Las propuestas no están numeradas como decisiones: quedan abiertas hasta que el
arquitecto las resuelva y se registren como D-n.

### Revisión del detector de picos tras la corrida real (2026-11-20)

- **Estado:** parcialmente resuelta por D15 (2026-11-20): resolución de la
  ventana, regla de selección y arnés de evaluación. Queda abierta solo en lo
  no decidido, abajo.
- **Datos de la corrida real** (VOD de Rubius, 8:34:30, nota de sesión de la
  fase 4):
  - Mediana de 544 mensajes por minuto y máximo de ×1,31.
  - 39 minutos por encima de ×1,2, solo 1 por encima de ×1,3 y ninguno por
    encima del umbral ×1,5 (D10).
  - Los 10 clips de referencia caen en minutos de ×0,58 a ×1,30.
  - Resultado: 0 candidatos, 0 llamadas al juez, 0/10 clips.
- **Resuelto en D15:** la resolución (ventana deslizante de 60 s sobre un array
  por segundo), la selección (top-K con supresión de no-máximos en lugar del
  umbral ×1,5), la línea base por defecto (mediana global) y el arnés de
  evaluación sin juez con su criterio de aceptación. Las dos lecturas que
  traía esta propuesta (calibración y señal) quedan respondidas por los
  hallazgos F2 y F3 de D15.
- **Sigue abierto, sin decidir:**
  - **Línea base local o rodante** en lugar de la mediana global, para
    directos de 8,5 h con fases distintas. No se decide con el fixture de
    Rubius: su referencia está contaminada por fase (D15, F3). No entra en la
    fase 5.
  - **Señales complementarias** al volumen, sin pesos ni léxicos fijados hasta
    que lo confirme más de una VOD:
    - Usuarios únicos por minuto. Exige un campo `user` en `ChatEvent`, que
      hoy solo tiene `t_s` y `message`. Se plantea como requisito de ingesta
      de la v2: cambiaría la SPEC §4, los cargadores, el CSV y los datos de
      demostración.
    - Densidad de emotes. Sin metadatos de emotes solo hay proxies de texto:
      un léxico a mano (dependiente del idioma y del streamer, fácil de
      sobreajustar) o la ráfaga por token, sin léxico.
    - Mensajes distintos por ventana, calculable sin cambiar el contrato.
    - Densidad de habla de la transcripción, solo como señal de selección y
      nunca como puntos de `reaccion_chat`; exigiría deduplicar las
      alucinaciones de Whisper.
  - **Segunda VOD de validación**, de otro tipo de streamer (chat pequeño, no
    un mega-directo), para comprobar que el detector generaliza y para decidir
    la línea base. Hay que descargarla, así que necesita el OK del arquitecto.
- **Fixture:** el dataset de Rubius (`chat.json`, `transcript.json` y
  `reference.json` en `~/rubius-run`, fuera del repo) queda como fixture. La
  primera corrida de la fase 5 con el detector revisado se hace sobre estos
  mismos datos, sin descargar nada, y ahí se cierra también la validación del
  juez (D15).
