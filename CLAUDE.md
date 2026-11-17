# CLAUDE.md — gta6-clipping-agent

Reglas permanentes del proyecto. Se leen al empezar cada sesión y prevalecen
sobre cualquier idea de mejora que surja por el camino.

## Qué es

Detector agéntico de momentos clipeables de GTA 6 en VODs de streamers en
español. Es un proyecto de aprendizaje de AI Engineering aplicado: cada pieza
tiene que poder entenderse, por eso el orquestador es nuestro, simple y
explícito. La spec completa está en [SPEC.md](SPEC.md).

## Restricciones duras

1. **Nunca se sube ni se publica nada.** Este sistema no sube ni publica en
   TikTok, YouTube, Instagram ni en ninguna otra plataforma. No se escribe
   código de subida ni clientes de APIs de publicación, y tampoco se propone.
   El flujo termina en una lista de momentos propuestos (JSON); el humano
   revisa y sube a mano.
2. **El detector es agnóstico a la fuente.** El núcleo recibe trozos
   normalizados (`segments`, `chat_events`), nunca una URL ni una ruta de
   fichero. Leer ficheros es trabajo de los cargadores, que viven fuera del
   detector.
3. **La reacción del chat la mide código determinista.** El LLM nunca estima
   `reaccion_chat`; solo juzga contexto, novedad y gancho.
4. **Sin frameworks de agentes en v0.** Nada de LangChain, LangGraph ni
   similares. Se usa directamente el SDK oficial de Anthropic.
5. **Los secretos no entran en el repo.** La API key va en `.env`, que está en
   `.gitignore`. `.env.example` lista las variables sin valores.
6. **No se añade nada fuera de alcance sin preguntar.** La arquitectura y las
   decisiones ya están tomadas. Si algo parece útil y no está en SPEC.md, se
   pregunta antes y la propuesta se registra en
   [docs/DECISIONS.md](docs/DECISIONS.md).

## Stack

- Python 3.11+
- `anthropic` (SDK oficial)
- `pydantic` (modelos internos y validación de la salida del juez)
- `pytest`
- `python-dotenv`

## Estructura

```
CLAUDE.md          reglas permanentes (este fichero)
SPEC.md            spec v0
PROGRESS.md        estado de las fases
README.md          qué es y cómo se arranca
.env.example       variables de entorno sin valores (.env nunca se commitea)
docs/DECISIONS.md  decisiones fechadas y propuestas fuera de alcance
docs/sessions/     una nota por fase cerrada
src/               código
tests/             tests (pytest)
```

## Método de trabajo

- Fases pequeñas, en el orden de [PROGRESS.md](PROGRESS.md).
- Antes de escribir código en una fase: explicar en 3-5 frases qué se va a
  hacer y por qué, y esperar el OK.
- Una fase solo está hecha con todos los tests en verde. Si un test falla, la
  fase no se marca como hecha.
- Ningún test llama a la API real de Claude: la API siempre se mockea.
- Al cerrar cada fase:
  1. tests en verde (`python -m pytest`);
  2. actualizar PROGRESS.md;
  3. nota en `docs/sessions/AAAA-MM-DD-fase-N.md` con qué se hizo, tests,
     errores y la lección en una frase;
  4. un commit separado para la fase.
- Flujo de ramas y PRs (D6):
  - Cada fase va en su rama `fase-N/descripcion-corta`, creada desde `main`
    actualizado y solo tras el OK de la fase (por ejemplo,
    `fase-1/modelos-ingesta`).
  - Al cerrar la fase, Claude Code abre la PR contra `main` con `gh`.
  - La fusión la hace solo una persona, con los tests en verde. Claude Code
    nunca fusiona.
  - Excepción: los cambios que solo tocan documentación van directos a
    `main`.
  - No hay protección de rama en GitHub por ahora: la regla se sostiene por
    convención, así que no se empuja código a `main` sin PR.
- CHANGELOG (convención propia): `CHANGELOG.md` sigue Keep a Changelog. Toda
  PR añade su entrada en `## [Unreleased]` antes de fusionarse.
