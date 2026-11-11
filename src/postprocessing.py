"""Stable binary postprocessing; temperature fitting never changes network weights."""

import math

import numpy as np


def sigmoid(values):
    values = np.asarray(values, dtype=np.float64)
    if not np.isfinite(values).all():
        raise ValueError('Logit margins must be finite.')
    return np.exp(-np.logaddexp(0., -values))


def probability_to_margin(threshold):
    if (isinstance(threshold, bool) or not isinstance(threshold, (int, float, np.number))
            or not math.isfinite(float(threshold)) or not 0 < threshold < 1):
        raise ValueError('A finite margin boundary requires a probability threshold strictly between 0 and 1.')
    return math.log(threshold) - math.log1p(-threshold)


def check_arrays(targets, margins):
    truth, margins = np.asarray(targets), np.asarray(margins, dtype=np.float64)
    if truth.ndim != 1 or margins.shape != truth.shape or set(truth.tolist()) != {0, 1} or not np.isfinite(margins).all():
        raise ValueError('Require finite one-dimensional margins and both binary classes.')
    return truth.astype(int), margins


def probability_quality(targets, margins, temperature=1.):
    truth, margins = check_arrays(targets, margins)
    if not math.isfinite(temperature) or temperature <= 0:
        raise ValueError('Temperature must be finite and positive.')
    scaled = margins / temperature
    probabilities = sigmoid(scaled)
    # softplus(-signed margin) avoids cancellation in log(1 - saturated probability).
    signed = scaled * (2 * truth - 1)
    loss = np.logaddexp(0., -signed)
    bins = np.minimum((probabilities * 10).astype(int), 9)
    reliability = []
    error = 0.
    for index in range(10):
        chosen = bins == index
        count = int(chosen.sum())
        if count:
            average, observed = float(probabilities[chosen].mean()), float(truth[chosen].mean())
            error += count / len(truth) * abs(average - observed)
            reliability.append(dict(bin=index, images=count, mean_score=average, observed_positive_fraction=observed))
    return dict(images=len(truth), negative_log_likelihood=float(loss.mean()),
                brier_score=float(((probabilities - truth)**2).mean()), expected_calibration_error_10_bins=float(error),
                reliability_bins=reliability, temperature=float(temperature))


def fit_temperature(targets, margins, bounds=(.05, 100.)):
    """Solve convex NLL in inverse temperature by bisection; one scalar, no neural optimizer."""
    truth, margins = check_arrays(targets, margins)
    minimum, maximum = bounds
    if not 0 < minimum < maximum or not math.isfinite(maximum):
        raise ValueError('Invalid temperature bounds.')
    lower, upper = 1 / maximum, 1 / minimum

    def derivative(inverse):
        return float((margins * (sigmoid(inverse * margins) - truth)).mean())

    if derivative(lower) >= 0:
        inverse, bound = lower, 'maximum_temperature'
    elif derivative(upper) <= 0:
        inverse, bound = upper, 'minimum_temperature'
    else:
        for _ in range(100):
            middle = (lower + upper) / 2
            if derivative(middle) > 0:
                upper = middle
            else:
                lower = middle
        inverse, bound = (lower + upper) / 2, None
    return dict(temperature=float(1 / inverse), method='bounded_convex_inverse_temperature_bisection',
                bounds=list(bounds), bound_hit=bound)


def validate_profile(profile, checkpoint_sha256):
    if (profile.get('schema_version') != 1 or profile.get('kind') != 'experimental_temperature_scaling'
            or profile.get('checkpoint_sha256') != checkpoint_sha256
            or profile.get('decision_policy') != 'preserve_original_margin_boundary'):
        raise ValueError('Postprocessing profile is unsupported or belongs to another checkpoint.')
    temperature = profile.get('temperature')
    threshold = profile.get('decision_margin_threshold')
    if (isinstance(temperature, bool) or not isinstance(temperature, (int, float))
            or not math.isfinite(temperature) or temperature <= 0
            or isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold)):
        raise ValueError('Profile requires a positive finite temperature and finite margin threshold.')
    original = profile.get('original_probability_threshold')
    if original is None or not math.isclose(threshold, probability_to_margin(original), rel_tol=0, abs_tol=1e-12):
        raise ValueError('The profile must preserve the original decision boundary.')
    return profile
