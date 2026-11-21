# gta6-clipping-agent

Detector de momentos clipeables de GTA 6 en VODs de streamers en español o en
inglés. Recibe la transcripción y el chat de un VOD y propone los 5 mejores
momentos para clipear en un JSON.

No publica nada: la revisión y la subida de clips se hacen a mano.

El estado de cada fase está en [PROGRESS.md](PROGRESS.md).

## Puesta en marcha

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # y rellena GEMINI_API_KEY
ruff check . && black --check . && python -m pytest   # lo mismo que ejecuta el CI
```

## Uso

```bash
python -m src.main --transcript examples/demo/transcript.json --chat examples/demo/chat.json --out resultados.json --reference examples/demo/reference.json
```

Argumentos:

- `--transcript`: transcripción del VOD, en JSON o CSV (claves `start_s`,
  `end_s`, `text`). Obligatorio.
- `--chat`: chat del VOD, en JSON o CSV (claves `t_s`, `message`). Obligatorio.
- `--out`: dónde se escribe la lista de momentos propuestos (JSON). Obligatorio.
- `--reference`: opcional. Clips de referencia (por ejemplo, los más vistos de
  Twitch de ese VOD), en JSON o CSV con las claves `start_s` y `end_s` (las
  demás se ignoran). Si se pasa, se imprime cuántos de esos clips detecta el
  agente entre sus momentos propuestos (acierto = solape de ±60 s).

Los tiempos de todos los ficheros pueden ir en segundos o como `"HH:MM:SS"`.

La clave `GEMINI_API_KEY` tiene que estar en `.env` (ver `.env.example`). Sin
ella el comando falla antes de procesar nada.

`examples/demo/` trae datos sintéticos de 90 minutos para probar el flujo. Con el
detector de la fase 5 (D15) da 20 candidatos de 135 s. Los tres primeros
(540-675 s, 1978-2113 s y 4139-4274 s) son los picos plantados; los otros 17 se
dan con 13 mensajes por minuto (×1,08). El fichero de salida tiene como máximo 5
momentos, así que la evaluación del CLI mide esos 5, no los 20 candidatos. La
referencia de la demo ya no discrimina: 20 candidatos de 135 s cubren unos 45 de
los 90 minutos. Sirve para probar el flujo, no como medida (ver la nota de
sesión de la fase 5).

Códigos de salida: `0` si todo va bien, `1` en un error fatal (falta la clave,
un fichero no existe o no es válido, la ruta de `--out` no se puede escribir o
pisaría un fichero de entrada, el chat no tiene actividad suficiente, o todos
los candidatos fallan: en ese caso el fichero de `--out` no se crea ni se
sobrescribe), `2` si los argumentos son incorrectos y `130` si se interrumpe
con Ctrl+C. La ruta de `--out` se comprueba antes de llamar al juez. Un
candidato que falla dos veces en el juez no es fatal mientras algún otro
produzca un momento: se cuenta en `Candidate errors` y el resto sigue adelante.
Con un chat con actividad, el detector siempre propone candidatos (hasta 20), así
que `[]` solo aparece si el generador se sustituye. Un chat sin actividad (o con
tan poca que su media queda por debajo de 1 mensaje/minuto, D17) sale con `1` y
el error `chat sin actividad suficiente`; un chat de más de 48 h, con `1` y un
error que nombra el valor; y una referencia sin clips, con `1` y
`reference has no clips`, antes de llamar al juez.

Ritmo del juez (D16, SPEC §8): `GeminiJudge` deja al menos 12 s entre llamadas
a la API, por el techo de 5 peticiones por minuto del tier gratuito, así que 20
candidatos tardan unos 4 minutos como mínimo. Un 429, un 503 o un fallo de red se
reintentan esperando (el `retryDelay` del servidor o un retroceso de 15 s y 30 s),
hasta 3 intentos por candidato.

El sistema no sube ni publica nada: el resultado es un JSON para que lo
revises y subas a mano.

Formato de lo que imprime. Las cifras son marcadores, no una medida: los valores
reales dependen del juez LLM.

```text
Moments: N written to resultados.json
Candidate errors: N
Judge usage: N calls, N input tokens, N output tokens
Evaluation: N/M reference clips detected (tolerance +/-60 s)
  - HH:MM:SS-HH:MM:SS: detected|missed
Pending human review: this agent never uploads or publishes anything.
```

Y un elemento de `resultados.json` (también ilustrativo, con valores inventados):

```json
{
  "inicio": "00:33:30",
  "fin": "00:34:10",
  "puntuacion": 83,
  "desglose": {
    "reaccion_chat": 28,
    "contexto": 22,
    "novedad": 18,
    "gancho": 15
  },
  "categoria": "bug gracioso",
  "gancho": "Esto no deberia pasar en GTA 6",
  "chat": {
    "msg_min": 48.0,
    "multiplicador": 4.0
  }
}
```

## Arnés sin juez

Para comparar configuraciones del detector sin gastar cuota del juez:

```bash
python -m src.harness --chat examples/demo/chat.json --reference examples/demo/reference.json
```

Informa de aciertos@K para K = 5, 10, 20 y 40 sobre los candidatos del detector
(no sobre los momentos del juez), y también de `--k` si no está en esa lista.
Compara con un azar con p-valor por permutación, que sortea los inicios con la
misma separación mínima que el detector (120 s), y da un veredicto PASS/FAIL
según el criterio de D15. Opciones: `--window-s` (60), `--k` (20), `--trials`
(2000, mínimo 20) y `--seed` (0). Sale con `0` también con FAIL, `1` si un
fichero no existe o no es válido (una referencia sin clips incluida), si el chat
no tiene actividad suficiente o si dura más de 48 h, `2` si los argumentos son
inválidos y `130` si se interrumpe. Detalle en la sección 9.1 de la
[SPEC](SPEC.md).

## Documentos

- [SPEC.md](SPEC.md): spec v0 (entradas, salida, rúbrica, criterios de aceptación)
- [CLAUDE.md](CLAUDE.md): reglas permanentes del proyecto
- [docs/DECISIONS.md](docs/DECISIONS.md): decisiones registradas
- [docs/sessions/](docs/sessions/): notas por fase
