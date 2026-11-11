"""Binary operating metrics and stable logit diagnostics without model fitting."""

import numpy as np
import torch


def binary_score_details(logits):
    """Stable ranking/log scores plus legacy float32 probabilities for compatible decisions."""
    if logits.ndim != 2 or logits.shape[1] != 2 or not bool(torch.isfinite(logits).all()):
        raise ValueError('Expected finite Nx2 logits.')
    values = logits.detach().to(dtype=torch.float64)
    return dict(probabilities_float32=torch.softmax(logits.float(), dim=1),
                logit_margins=values[:, 1] - values[:, 0],
                log_probabilities=torch.log_softmax(values, dim=1))


def metrics(targets, scores, threshold=0.5):
    from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix, roc_auc_score
    truth, scores = np.asarray(targets), np.asarray(scores)
    if set(truth.tolist()) != {0, 1} or not np.isfinite(scores).all():
        raise ValueError('Evaluation requires both classes and finite scores.')
    predictions = (scores >= threshold).astype(int)
    tn, fp, fn, tp = (int(value) for value in confusion_matrix(truth, predictions, labels=[0, 1]).ravel())
    return dict(accuracy=float(accuracy_score(truth, predictions)),
                balanced_accuracy=float(balanced_accuracy_score(truth, predictions)),
                roc_auc=float(roc_auc_score(truth, scores)),
                sensitivity=tp / (tp + fn), specificity=tn / (tn + fp),
                threshold=float(threshold), confusion_matrix=dict(TN=tn, FP=fp, FN=fn, TP=tp))


def score_logits(targets, logits, threshold, probabilities=None):
    """Keep the saved probability decision while measuring ranking without softmax ties."""
    from sklearn.metrics import roc_auc_score
    values = torch.as_tensor(logits, dtype=torch.float64, device='cpu')
    truth = np.asarray(targets)
    if (values.ndim != 2 or values.shape != (len(truth), 2) or not bool(torch.isfinite(values).all())
            or set(truth.tolist()) != {0, 1} or not 0 <= threshold <= 1):
        raise ValueError('Require finite Nx2 logits, both binary classes, and a valid saved threshold.')
    # Match the historical float32-softmax decision, even when scores have saturated.
    probabilities = (torch.softmax(values.float(), dim=1)[:, 1].numpy() if probabilities is None
                     else np.asarray(probabilities, dtype=np.float32))
    if probabilities.shape != (len(truth),) or not np.isfinite(probabilities).all() or ((probabilities < 0) | (probabilities > 1)).any():
        raise ValueError('Require one finite probability in [0, 1] per image.')
    margins = (values[:, 1] - values[:, 0]).numpy()
    log_probabilities = binary_score_details(values)['log_probabilities'].numpy()
    nll = -log_probabilities[np.arange(len(truth)), truth.astype(int)]
    result = metrics(truth, probabilities, threshold)
    return dict(metrics_at_saved_threshold=result,
                roc_auc_logit_margin=float(roc_auc_score(truth, margins)),
                loss_from_logits=float(nll.mean()),
                score_saturation={label: dict(
                    images=int((truth == target).sum()),
                    score_exactly_one=int(((truth == target) & (probabilities == 1)).sum()),
                    score_exactly_zero=int(((truth == target) & (probabilities == 0)).sum()))
                    for target, label in enumerate(('NORMAL', 'PNEUMONIA'))},
                targets=truth.astype(int).tolist(), logits=values.tolist(), margins=margins.tolist(),
                scores=probabilities.tolist(), log_probabilities=log_probabilities.tolist(), nll=nll.tolist())


def collect_logits(model, loader, device, amp=False, progress=print):
    """Read-only inference: no optimizer, gradients, fitting, or threshold selection."""
    model.eval()
    targets, logits, probabilities = [], [], []
    with torch.inference_mode():
        for batch_index, (inputs, labels) in enumerate(loader):
            with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=amp):
                output = model(inputs.to(device))
            if output.shape != (len(labels), 2) or not bool(torch.isfinite(output).all()):
                raise ValueError('Expected finite Nx2 model outputs; diagnostic stopped.')
            logits.extend(output.detach().float().cpu().tolist())
            probabilities.extend(torch.softmax(output.float(), dim=1)[:, 1].cpu().tolist())
            targets.extend(labels.tolist())
            if (batch_index + 1) % 25 == 0 or batch_index + 1 == len(loader):
                progress(f'Inference batch {batch_index + 1}/{len(loader)}; images={len(targets)}')
    return targets, logits, probabilities
