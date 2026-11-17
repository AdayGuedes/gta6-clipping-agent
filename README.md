# gta6-clipping-agent

Detector de momentos clipeables de GTA 6 en VODs de streamers en español.
Recibe la transcripción y el chat de un VOD y propone los 5 mejores momentos
para clipear en un JSON.

No publica nada: la revisión y la subida de clips se hacen a mano.

El estado de cada fase está en [PROGRESS.md](PROGRESS.md).

## Puesta en marcha

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pytest          # el resto de dependencias llega en la fase 1
cp .env.example .env        # y rellena ANTHROPIC_API_KEY
python -m pytest
```

## Uso (fase 4, todavía no disponible)

```bash
python -m src.main --transcript <fichero> --chat <fichero> --out resultados.json
```

## Documentos

- [SPEC.md](SPEC.md): spec v0 (entradas, salida, rúbrica, criterios de aceptación)
- [CLAUDE.md](CLAUDE.md): reglas permanentes del proyecto
- [docs/DECISIONS.md](docs/DECISIONS.md): decisiones registradas
- [docs/sessions/](docs/sessions/): notas por fase
