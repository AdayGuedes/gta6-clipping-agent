from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from src.models import Moment, ReferenceClip
from src.timeparse import hhmmss_to_seconds, seconds_to_hhmmss

TOLERANCE_S = 60


class ClipResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clip: ReferenceClip
    detected: bool


class EvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    detected: int
    clips: list[ClipResult]


def _matches(moment: Moment, clip: ReferenceClip) -> bool:
    moment_start = hhmmss_to_seconds(moment.inicio)
    moment_end = hhmmss_to_seconds(moment.fin)
    return (
        moment_start <= clip.end_s + TOLERANCE_S
        and moment_end >= clip.start_s - TOLERANCE_S
    )


def evaluate(
    moments: Sequence[Moment], reference: Sequence[ReferenceClip]
) -> EvaluationReport:
    clips = [
        ClipResult(clip=clip, detected=any(_matches(m, clip) for m in moments))
        for clip in reference
    ]
    return EvaluationReport(
        total=len(clips),
        detected=sum(result.detected for result in clips),
        clips=clips,
    )


def format_report(report: EvaluationReport) -> list[str]:
    summary = (
        f"Evaluation: {report.detected}/{report.total} reference clips detected "
        f"(tolerance +/-{TOLERANCE_S} s)"
    )
    lines = [summary]
    for result in report.clips:
        status = "detected" if result.detected else "missed"
        lines.append(
            f"  - {seconds_to_hhmmss(result.clip.start_s)}-"
            f"{seconds_to_hhmmss(result.clip.end_s)}: {status}"
        )
    return lines
