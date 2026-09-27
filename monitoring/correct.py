"""Bias-corrected failure prevalence for a monitoring period."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np


def corrected_mode_prevalence(
    sample_preds: Sequence[int],
    test_labels: Sequence[int],
    test_preds: Sequence[int],
    confidence: float = 0.95,
    bootstrap_iterations: int = 20000,
    seed: int | None = 7,
) -> dict[str, Any]:
    """Bias-corrected live prevalence for one mode from sampled verdicts.

    The contract, precisely:

      1. ``raw`` is the uncorrected flag rate: ``mean(sample_preds)``.
      2. Compute the frozen judge's failure sensitivity and pass specificity
         from ``test_labels`` and ``test_preds``. Both use the monitoring
         convention that 1 means a failure is present. Failure sensitivity is
         the flagged fraction of human-labeled failures. Pass specificity is
         the unflagged fraction of human-labeled passes.
      3. Compute the Rogan-Gladen point estimate, then resample the held-out
         records and sampled predictions to obtain a percentile-bootstrap
         interval. Use a seeded NumPy generator so the committed result is
         reproducible.
      4. Resample the monitoring predictions and the paired held-out records
         independently with replacement. Keep their original sample sizes.
         Discard a draw if the correction cannot be computed. Clamp each
         retained estimate to [0, 1], then take the percentile interval.
         Raise ``ValueError`` if no replicate is valid.

    Args:
        sample_preds: the judge's 0/1 verdicts over the UNIFORM BASE sample
            only (never the risk strata; they are biased toward failure by
            design).
        test_labels: human labels for the frozen Homework 5 judge's test
            split.
        test_preds: the frozen judge's predictions on that test split.
        confidence: interval confidence level.
        bootstrap_iterations: number of percentile-bootstrap replicates.
        seed: numpy seed for a reproducible interval; None leaves the RNG
            untouched.

    Returns:
        {"raw", "corrected", "ci_low", "ci_high", "confidence",
         "failure_sensitivity", "pass_specificity", "n_sample"}
        with "corrected" clamped to [0, 1] and rates rounded to 4 places.

    Raises:
        ValueError: if an input is empty, the held-out inputs have different
            lengths, a value is not 0 or 1, a class is absent, the judge is
            missing a usable correction, or no bootstrap replicate is valid.
    """
    sample_preds = list(sample_preds)
    test_labels = list(test_labels)
    test_preds = list(test_preds)
    if not sample_preds:
        raise ValueError("sample_preds must be non-empty")
    if not test_labels or not test_preds:
        raise ValueError("test_labels and test_preds must be non-empty")
    if len(test_labels) != len(test_preds):
        raise ValueError("test_labels and test_preds must have the same length")
    for values in (sample_preds, test_labels, test_preds):
        if any(value not in (0, 1) for value in values):
            raise ValueError("all values must be 0 or 1")

    def _rates(labels: list[int], preds: list[int]) -> tuple[float, float] | None:
        positives = [p for l, p in zip(labels, preds) if l == 1]
        negatives = [p for l, p in zip(labels, preds) if l == 0]
        if not positives or not negatives:
            return None
        sensitivity = sum(positives) / len(positives)
        specificity = 1 - sum(negatives) / len(negatives)
        return sensitivity, specificity

    def _rogan_gladen(raw: float, sensitivity: float, specificity: float) -> float | None:
        denom = sensitivity + specificity - 1
        if denom == 0:
            return None
        return (raw + specificity - 1) / denom

    rates = _rates(test_labels, test_preds)
    if rates is None:
        raise ValueError("test_labels must contain both classes")
    failure_sensitivity, pass_specificity = rates

    raw = sum(sample_preds) / len(sample_preds)
    corrected = _rogan_gladen(raw, failure_sensitivity, pass_specificity)
    if corrected is None:
        raise ValueError("the judge is missing a usable correction")
    corrected = min(1.0, max(0.0, corrected))

    rng = np.random.default_rng(seed)
    sample_arr = np.array(sample_preds)
    label_arr = np.array(test_labels)
    pred_arr = np.array(test_preds)
    n_sample_draw = len(sample_preds)
    n_test_draw = len(test_labels)

    replicates: list[float] = []
    for _ in range(bootstrap_iterations):
        sample_idx = rng.integers(0, n_sample_draw, size=n_sample_draw)
        test_idx = rng.integers(0, n_test_draw, size=n_test_draw)
        boot_labels = label_arr[test_idx].tolist()
        boot_preds = pred_arr[test_idx].tolist()
        boot_rates = _rates(boot_labels, boot_preds)
        if boot_rates is None:
            continue
        boot_raw = float(sample_arr[sample_idx].mean())
        boot_corrected = _rogan_gladen(boot_raw, *boot_rates)
        if boot_corrected is None:
            continue
        replicates.append(min(1.0, max(0.0, boot_corrected)))

    if not replicates:
        raise ValueError("no valid bootstrap replicate")

    alpha = (1 - confidence) / 2
    ci_low = float(np.percentile(replicates, alpha * 100))
    ci_high = float(np.percentile(replicates, (1 - alpha) * 100))

    return {
        "raw": round(raw, 4),
        "corrected": round(corrected, 4),
        "ci_low": round(ci_low, 4),
        "ci_high": round(ci_high, 4),
        "confidence": confidence,
        "failure_sensitivity": round(failure_sensitivity, 4),
        "pass_specificity": round(pass_specificity, 4),
        "n_sample": len(sample_preds),
    }
