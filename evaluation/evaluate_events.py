"""Compare predicted event timestamps with human-labelled ground truth."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean, median

from schemas import VideoAnalysis


@dataclass(frozen=True)
class EvaluationResult:
    precision: float
    recall: float
    f1: float
    matched_events: int
    false_positives: int
    false_negatives: int
    mean_timestamp_error: float | None
    median_timestamp_error: float | None


def _singular(name: str) -> str:
    aliases = {"kills": "kill", "headshots": "headshot", "deaths": "death", "clutches": "clutch"}
    return aliases.get(name, name)


def evaluate_events(
    predictions: VideoAnalysis,
    ground_truth: dict[str, list[float]],
    tolerance: float = 2,
) -> EvaluationResult:
    if tolerance < 0:
        raise ValueError("tolerance must be non-negative")
    predicted = [(event.type, event.timestamp) for event in predictions.events]
    actual = [
        (_singular(kind), float(timestamp))
        for kind, values in ground_truth.items()
        for timestamp in values
    ]
    candidates = sorted(
        (abs(predicted_time - actual_time), predicted_index, actual_index)
        for predicted_index, (predicted_type, predicted_time) in enumerate(predicted)
        for actual_index, (actual_type, actual_time) in enumerate(actual)
        if predicted_type == actual_type and abs(predicted_time - actual_time) <= tolerance
    )
    used_predictions: set[int] = set()
    used_actual: set[int] = set()
    errors: list[float] = []
    for error, predicted_index, actual_index in candidates:
        if predicted_index not in used_predictions and actual_index not in used_actual:
            used_predictions.add(predicted_index)
            used_actual.add(actual_index)
            errors.append(error)
    matched = len(errors)
    false_positives = len(predicted) - matched
    false_negatives = len(actual) - matched
    precision = matched / len(predicted) if predicted else (1.0 if not actual else 0.0)
    recall = matched / len(actual) if actual else (1.0 if not predicted else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return EvaluationResult(
        precision=precision,
        recall=recall,
        f1=f1,
        matched_events=matched,
        false_positives=false_positives,
        false_negatives=false_negatives,
        mean_timestamp_error=mean(errors) if errors else None,
        median_timestamp_error=median(errors) if errors else None,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("predictions", type=Path, help="VideoAnalysis JSON file")
    parser.add_argument("ground_truth", type=Path, help="Ground-truth JSON file")
    parser.add_argument("--tolerance", type=float, default=2)
    arguments = parser.parse_args()
    predictions = VideoAnalysis.model_validate_json(arguments.predictions.read_text())
    truth = json.loads(arguments.ground_truth.read_text())
    print(json.dumps(asdict(evaluate_events(predictions, truth, arguments.tolerance)), indent=2))


if __name__ == "__main__":
    main()
