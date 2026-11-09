"""Evaluate the deployed inference engine once at its saved threshold; never tune or train."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def evaluate_backend(data_dir, output):
    import torch
    from sklearn.metrics import (
        accuracy_score, average_precision_score, balanced_accuracy_score,
        confusion_matrix, f1_score, roc_auc_score,
    )
    from src.api.model_service import DenseNetInferenceEngine

    engine = DenseNetInferenceEngine()
    rows, targets, predictions, scores = [], [], [], []
    start = time.perf_counter()
    for label, target in [('NORMAL', 0), ('PNEUMONIA', 1)]:
        folder = data_dir / 'test' / label
        if not folder.is_dir():
            raise ValueError(f'Missing test class directory: {folder}')
        files = [path for path in sorted(folder.rglob('*')) if path.is_file() and not path.name.startswith('.')]
        if not files:
            raise ValueError(f'Empty test class directory: {folder}')
        for path in files:
            payload = path.read_bytes()
            result = engine.predict(payload)
            target_class = result['prediction'] == 'PNEUMONIA'
            targets.append(target)
            predictions.append(int(target_class))
            scores.append(result['pneumonia_probability'])
            rows.append(dict(path=path.relative_to(data_dir).as_posix(), label=label,
                             sha256=hashlib.sha256(payload).hexdigest(), **result))
            if len(rows) % 100 == 0:
                print(f'Evaluated {len(rows)} test images on {engine.device} ...', flush=True)
    tn, fp, fn, tp = (int(value) for value in confusion_matrix(targets, predictions, labels=[0, 1]).ravel())
    metrics = dict(
        samples=len(rows), accuracy=accuracy_score(targets, predictions),
        balanced_accuracy=balanced_accuracy_score(targets, predictions),
        sensitivity=tp / (tp + fn), specificity=tn / (tn + fp),
        precision_pneumonia=tp / (tp + fp) if tp + fp else 0.0,
        macro_f1=f1_score(targets, predictions, average='macro', zero_division=0),
        roc_auc=roc_auc_score(targets, scores), average_precision=average_precision_score(targets, scores),
        confusion_matrix=dict(TN=tn, FP=fp, FN=fn, TP=tp),
    )
    report = dict(
        created_at=datetime.now(timezone.utc).isoformat(), data_root=str(data_dir.resolve()),
        checkpoint=str(engine.checkpoint_path.resolve()),
        checkpoint_sha256=hashlib.sha256(engine.checkpoint_path.read_bytes()).hexdigest(),
        torch_version=torch.__version__, device=str(engine.device), threshold=engine.threshold,
        elapsed_seconds=round(time.perf_counter() - start, 2), metrics=metrics,
        scope='Fixed checkpoint and saved threshold; no threshold search, weight updates, or server. '
              'Runs the backend validation/preprocessing/prediction path directly. '
              'AUC uses the API\'s four-decimal scores. Patient independence and checkpoint provenance are unverified.',
        predictions=rows,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({key: report[key] for key in report if key != 'predictions'}, indent=2))
    print(f'Full report: {output}. No model weights or dataset images were changed.')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path('data'))
    parser.add_argument('--output', type=Path, default=Path('data/review/model_baseline.json'))
    args = parser.parse_args()
    evaluate_backend(args.data_dir, args.output)


if __name__ == '__main__':
    main()
