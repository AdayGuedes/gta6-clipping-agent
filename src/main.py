import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, TextIO, runtime_checkable

from src.evaluate import evaluate, format_report
from src.judge import GeminiJudge, Judge, JudgeConfigError, judge_candidates
from src.loaders import LoadError, load_chat, load_reference, load_transcript
from src.models import Moment
from src.peaks import InsufficientChatError, generate_candidates

EXIT_OK = 0
EXIT_FATAL = 1
EXIT_INTERRUPTED = 130

PENDING_REVIEW = "Pending human review: this agent never uploads or publishes anything."


@runtime_checkable
class ReportsUsage(Protocol):
    calls: int
    input_tokens: int
    output_tokens: int


def _usage_line(judge: Judge) -> str:
    if isinstance(judge, ReportsUsage):
        return (
            f"Judge usage: {judge.calls} calls, {judge.input_tokens} input tokens, "
            f"{judge.output_tokens} output tokens"
        )
    return "Judge usage: not reported by this judge"


class OutputPathError(ValueError):
    pass


class AllCandidatesFailedError(RuntimeError):
    pass


def _check_out_path(out_path: Path, input_paths: Sequence[Path]) -> None:
    target = out_path.resolve()
    if target.is_dir():
        raise OutputPathError(f"{out_path}: is a directory")
    parent = target.parent
    if not parent.is_dir():
        raise OutputPathError(f"{out_path}: parent directory does not exist")
    for input_path in input_paths:
        if target == input_path.resolve():
            raise OutputPathError(
                f"{out_path}: would overwrite the input file {input_path.name}"
            )
    writable_path = target if target.exists() else parent
    if not os.access(writable_path, os.W_OK):
        raise OutputPathError(f"{out_path}: not writable")


def _write_moments(out_path: Path, moments: Sequence[Moment]) -> None:
    content = json.dumps(
        [moment.model_dump(mode="json") for moment in moments],
        indent=2,
        ensure_ascii=False,
    )
    out_path.write_text(content + "\n", encoding="utf-8")


def run(
    transcript_path: Path,
    chat_path: Path,
    out_path: Path,
    judge: Judge,
    reference_path: Path | None = None,
    stream: TextIO | None = None,
) -> list[Moment]:
    inputs = [transcript_path, chat_path]
    if reference_path is not None:
        inputs.append(reference_path)
    _check_out_path(out_path, inputs)
    stream = sys.stdout if stream is None else stream

    segments = load_transcript(transcript_path)
    events = load_chat(chat_path)
    reference = None if reference_path is None else load_reference(reference_path)

    candidates = generate_candidates(events)
    moments, errors = judge_candidates(candidates, segments, judge)
    diagnostics = [f"Candidate errors: {len(errors)}"]
    diagnostics.extend(f"  - {error}" for error in errors)
    diagnostics.append(_usage_line(judge))

    if candidates and not moments:
        for line in diagnostics:
            print(line, file=stream)
        raise AllCandidatesFailedError(
            f"all {len(candidates)} candidates failed; output not written"
        )

    _write_moments(out_path, moments)

    lines = [f"Moments: {len(moments)} written to {out_path}", *diagnostics]
    if reference is not None:
        lines.extend(format_report(evaluate(moments, reference)))
    lines.append(PENDING_REVIEW)
    for line in lines:
        print(line, file=stream)
    return moments


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.main",
        description=(
            "Propose clippable GTA 6 moments from a VOD transcript and chat. "
            "The result is a JSON list for human review; nothing is uploaded."
        ),
    )
    parser.add_argument(
        "--transcript", required=True, type=Path, help="transcript (.json or .csv)"
    )
    parser.add_argument("--chat", required=True, type=Path, help="chat (.json or .csv)")
    parser.add_argument(
        "--out", required=True, type=Path, help="where to write the moments JSON"
    )
    parser.add_argument(
        "--reference",
        type=Path,
        help="optional reference clips (.json or .csv) to evaluate against",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        judge = GeminiJudge()
        run(args.transcript, args.chat, args.out, judge, args.reference)
    except (
        AllCandidatesFailedError,
        JudgeConfigError,
        LoadError,
        InsufficientChatError,
        OSError,
        OutputPathError,
        UnicodeDecodeError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_FATAL
    except KeyboardInterrupt:
        print("error: interrupted", file=sys.stderr)
        return EXIT_INTERRUPTED
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
