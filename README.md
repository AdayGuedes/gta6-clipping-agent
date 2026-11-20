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
  agente (acierto = solape de ±60 s).

Los tiempos de todos los ficheros pueden ir en segundos o como `"HH:MM:SS"`.

La clave `GEMINI_API_KEY` tiene que estar en `.env` (ver `.env.example`). Sin
ella el comando falla antes de procesar nada. `examples/demo/` trae datos
sintéticos de 90 minutos para probar el flujo.

Códigos de salida: `0` si todo va bien, `1` en un error fatal (falta la clave,
un fichero no existe o no es válido, la ruta de `--out` no se puede escribir o
pisaría un fichero de entrada, el chat no tiene actividad suficiente), `2` si
los argumentos son incorrectos y `130` si se interrumpe con Ctrl+C. La ruta de
`--out` se comprueba antes de llamar al juez. Un candidato que falla dos veces en el
juez no es fatal: se cuenta en `Candidate errors` y el resto sigue adelante.

El sistema no sube ni publica nada: el resultado es un JSON para que lo
revises y subas a mano.

Ejemplo ilustrativo de lo que imprime. Está generado con un juez falso sobre
los datos de `examples/demo/`, así que las puntuaciones son inventadas: las
reales vienen del juez LLM.

```text
Moments: 3 written to resultados.json
Candidate errors: 0
Judge usage: 3 calls, 2700 input tokens, 360 output tokens
Evaluation: 2/3 reference clips detected (tolerance +/-60 s)
  - 00:10:10-00:10:40: detected
  - 00:33:30-00:34:10: detected
  - 00:50:00-00:50:30: missed
Pending human review: this agent never uploads or publishes anything.
```

Y un elemento de `resultados.json` (también ilustrativo):

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

## Documentos

- [SPEC.md](SPEC.md): spec v0 (entradas, salida, rúbrica, criterios de aceptación)
- [CLAUDE.md](CLAUDE.md): reglas permanentes del proyecto
- [docs/DECISIONS.md](docs/DECISIONS.md): decisiones registradas
- [docs/sessions/](docs/sessions/): notas por fase
