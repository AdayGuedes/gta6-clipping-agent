import argparse
import random
import statistics
import sys
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TextIO

from src.evaluate import TOLERANCE_S, window_matches
from src.loaders import LoadError, load_chat, load_reference
from src.models import ChatEvent, ReferenceClip
from src.peaks import (
    DetectorConfig,
    InsufficientChatError,
    candidate_window,
    count_messages_per_second,
    generate_candidates,
    window_sums,
)

EXIT_OK = 0
EXIT_FATAL = 1
EXIT_INTERRUPTED = 130

REPORTED_K = (5, 10, 20, 40)
SIGNIFICANCE = 0.05

Window = tuple[float, float]


@dataclass(frozen=True)
class KResult:
    k: int
    candidates: int
    hits: int
    random_mean: float
    p_value: float


def count_hits(windows: Sequence[Window], reference: Sequence[ReferenceClip]) -> int:
    return sum(
        any(window_matches(start, end, clip) for start, end in windows)
        for clip in reference
    )


def random_hits(
    n_windows: int,
    positions: int,
    config: DetectorConfig,
    reference: Sequence[ReferenceClip],
    rng: random.Random,
) -> int:
    starts = rng.sample(range(positions), min(n_windows, positions))
    return count_hits([candidate_window(p, config) for p in starts], reference)


def evaluate_k(
    events: Sequence[ChatEvent],
    reference: Sequence[ReferenceClip],
    config: DetectorConfig,
    positions: int,
    trials: int,
    seed: int,
) -> KResult:
    candidates = generate_candidates(events, config=config)
    observed = count_hits([(c.start_s, c.end_s) for c in candidates], reference)
    rng = random.Random(seed)
    null = [
        random_hits(len(candidates), positions, config, reference, rng)
        for _ in range(trials)
    ]
    at_least = sum(hits >= observed for hits in null)
    return KResult(
        k=config.top_k,
        candidates=len(candidates),
        hits=observed,
        random_mean=statistics.fmean(null),
        p_value=(at_least + 1) / (trials + 1),
    )


def passes(result: KResult) -> bool:
    return result.candidates > 0 and result.p_value < SIGNIFICANCE


def run(
    chat_path: Path,
    reference_path: Path,
    config: DetectorConfig,
    trials: int,
    seed: int,
    stream: TextIO | None = None,
) -> bool:
    stream = sys.stdout if stream is None else stream
    events = load_chat(chat_path)
    reference = load_reference(reference_path)
    positions = len(window_sums(count_messages_per_second(events), config.window_s))

    ks = sorted({*REPORTED_K, config.top_k})
    results = {
        k: evaluate_k(
            events, reference, replace(config, top_k=k), positions, trials, seed
        )
        for k in ks
    }

    config_line = (
        f"Config: window {config.window_s} s, baseline {config.baseline}, "
        f"min separation {config.min_separation_s} s, lead {config.lead_s} s, "
        f"tail {config.tail_s} s"
    )
    lines = [
        f"Chat: {len(events)} messages, {positions} window positions",
        f"Reference clips: {len(reference)} (tolerance +/-{TOLERANCE_S} s)",
        config_line,
        f"Random baseline: {trials} trials, seed {seed}",
        "    K  candidates  hits  random mean  p-value",
    ]
    for result in results.values():
        lines.append(
            f"  {result.k:>3}  {result.candidates:>10}  "
            f"{result.hits:>2}/{len(reference):<2} {result.random_mean:>11.2f}  "
            f"{result.p_value:>7.4f}"
        )
    verdict = results[config.top_k]
    ok = passes(verdict)
    lines.append(
        f"Verdict (hits@{verdict.k} above random with p<{SIGNIFICANCE}, never "
        f"silent): {'PASS' if ok else 'FAIL'} - hits {verdict.hits}/{len(reference)}, "
        f"random mean {verdict.random_mean:.2f}, p={verdict.p_value:.4f}, "
        f"candidates {verdict.candidates}"
    )
    for line in lines:
        print(line, file=stream)
    return ok


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.harness",
        description=(
            "Measure chat-peak candidates against reference clips and a random "
            "baseline, without calling the judge."
        ),
    )
    parser.add_argument("--chat", required=True, type=Path, help="chat (.json or .csv)")
    parser.add_argument(
        "--reference",
        required=True,
        type=Path,
        help="reference clips (.json or .csv)",
    )
    parser.add_argument("--window-s", type=int, default=DetectorConfig.window_s)
    parser.add_argument("--k", type=int, default=DetectorConfig.top_k)
    parser.add_argument("--trials", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.trials < 1:
        parser.error("--trials must be at least 1")
    try:
        config = DetectorConfig(window_s=args.window_s, top_k=args.k)
    except ValueError as error:
        parser.error(str(error))
    try:
        run(args.chat, args.reference, config, args.trials, args.seed)
    except (LoadError, InsufficientChatError, OSError, UnicodeDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_FATAL
    except KeyboardInterrupt:
        print("error: interrupted", file=sys.stderr)
        return EXIT_INTERRUPTED
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
