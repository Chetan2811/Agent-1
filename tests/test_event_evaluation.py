import pytest

from evaluation.evaluate_events import evaluate_events
from schemas import VideoAnalysis
from services.montage_service import deduplicate_events


def test_evaluation_matches_each_label_once():
    predictions = VideoAnalysis.model_validate(
        {
            "events": [
                {"type": "kill", "timestamp": 10},
                {"type": "kill", "timestamp": 10.5},
                {"type": "death", "timestamp": 30},
            ]
        }
    )
    result = evaluate_events(predictions, {"kills": [11], "deaths": [40]}, tolerance=2)
    assert result.matched_events == 1
    assert result.false_positives == 2
    assert result.false_negatives == 1
    assert result.mean_timestamp_error == pytest.approx(0.5)


def test_deduplication_keeps_higher_confidence():
    analysis = VideoAnalysis.model_validate(
        {
            "events": [
                {"type": "kill", "timestamp": 4, "confidence": 0.5},
                {"type": "kill", "timestamp": 4.4, "confidence": 0.9},
            ]
        }
    )
    events = deduplicate_events(analysis.events, tolerance=1)
    assert len(events) == 1
    assert events[0].confidence == 0.9
