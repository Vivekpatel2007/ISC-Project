"""Manifest-based experiments. Model selection and threshold tuning use validation only."""

from collections import Counter
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import platform
import random
import sys
import time

import numpy as np
from PIL import Image
import torch
from torch.utils.data import DataLoader, Dataset

from src.compute import select_device
from src.data_protocol import CLASSES, ROOT, DatasetIntegrityError, read_verified_image
from src.modeling import NORMALIZATION, build_classifier, image_transforms, set_training_stage
from src.scoring import binary_score_details, metrics


class ManifestDataset(Dataset):
    def __init__(self, manifest, root, split, transform):
        self.rows = manifest['splits'][split]
        self.root, self.transform = root, transform
        self.targets = [CLASSES.index(row['label']) for row in self.rows]

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        payload = read_verified_image(self.root, row)
        with Image.open(io.BytesIO(payload)) as image:
            image.load()
            rgb = image.convert('RGB')
        return self.transform(rgb), self.targets[index]


def choose_threshold(targets, scores, min_sensitivity=0.95):
    if not 0 < min_sensitivity <= 1:
        raise ValueError('Validation sensitivity target must be in (0, 1].')
    truth, scores = np.asarray(targets), np.asarray(scores)
    if set(truth.tolist()) != {0, 1} or not np.isfinite(scores).all() or ((scores < 0) | (scores > 1)).any():
        raise ValueError('Invalid validation labels or probabilities.')
    choices = []
    unique = np.unique(scores)
    # Put cuts between observed scores rather than exactly on a validation float.
    thresholds = np.unique(np.r_[0.0, (unique[:-1] + unique[1:]) / 2, 1.0])
    for threshold in thresholds:
        positive = scores >= threshold
        sensitivity = float(positive[truth == 1].mean())
        specificity = float((~positive[truth == 0]).mean())
        if sensitivity >= min_sensitivity:
            choices.append(((sensitivity + specificity) / 2, specificity, float(threshold)))
    threshold = max(choices)[2]
    return metrics(truth, scores, threshold)


def seed_everything(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False


def rng_state(generator):
    numpy_state = np.random.get_state()
    return dict(python=random.getstate(), numpy=[numpy_state[0], numpy_state[1].tolist(), *numpy_state[2:]],
                torch=torch.get_rng_state(), cuda=torch.cuda.get_rng_state_all() if torch.cuda.is_available() else [],
                loader=generator.get_state())


def restore_rng(state, generator):
    random.setstate(state['python'])
    name, values, position, has_gauss, cached = state['numpy']
    np.random.set_state((name, np.array(values, dtype=np.uint32), position, has_gauss, cached))
    torch.set_rng_state(state['torch'])
    if state['cuda'] and torch.cuda.is_available():
        torch.cuda.set_rng_state_all(state['cuda'])
    generator.set_state(state['loader'])


def atomic_save(value, path):
    temporary = path.with_name(path.name + '.tmp')
    torch.save(value, temporary)
    os.replace(temporary, path)


def write_json(value, path):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def make_logger(run_dir):
    logger = logging.getLogger(f'pulmoscan.training.{run_dir}')
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)
    for handler in (logging.StreamHandler(sys.stdout), logging.FileHandler(run_dir / 'train.log', encoding='utf-8')):
        handler.setFormatter(logging.Formatter('%(asctime)s | %(message)s'))
        logger.addHandler(handler)
    return logger


def validate(model, loader, device, amp):
    model.eval()
    targets, scores, margins, total_loss = [], [], [], 0.0
    with torch.inference_mode():
        for inputs, labels in loader:
            inputs, labels = inputs.to(device), labels.to(device)
            with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=amp):
                logits = model(inputs)
            if not bool(torch.isfinite(logits).all()):
                raise ValueError('Non-finite validation logits; experiment stopped.')
            total_loss += float(torch.nn.functional.cross_entropy(logits.float(), labels, reduction='sum'))
            targets.extend(labels.cpu().tolist())
            scores.extend(torch.softmax(logits.float(), dim=1)[:, 1].cpu().tolist())
            margins.extend(binary_score_details(logits)['logit_margins'].cpu().tolist())
    return dict(loss=total_loss / len(targets), targets=targets, scores=scores, margins=margins,
                roc_auc_logit_margin=metrics(targets, margins, 0.)['roc_auc'], **metrics(targets, scores))


def train_epoch(model, loader, optimizer, scaler, device, weights, config, logger):
    accumulation = config['accumulation_steps']
    total_loss, correct, total = 0.0, 0, 0
    started = time.perf_counter()
    optimizer.zero_grad(set_to_none=True)
    for batch, (inputs, labels) in enumerate(loader):
        inputs, labels = inputs.to(device), labels.to(device)
        group_start = (batch // accumulation) * accumulation * loader.batch_size
        group_samples = min(accumulation * loader.batch_size, len(loader.dataset) - group_start)
        with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=scaler.is_enabled()):
            logits = model(inputs)
            # Sum then divide by accumulation-window sample count: weights still matter
            # with small/single-class batches, and the final partial window is correct.
            loss_sum = torch.nn.functional.cross_entropy(logits.float(), labels, weight=weights, reduction='sum')
        if not bool(torch.isfinite(loss_sum)):
            raise ValueError('Non-finite training loss; experiment stopped.')
        scaler.scale(loss_sum / group_samples).backward()
        if (batch + 1) % accumulation == 0 or batch + 1 == len(loader):
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), config['max_grad_norm'],
                                           error_if_nonfinite=not scaler.is_enabled())
            scale_before = scaler.get_scale()
            scaler.step(optimizer)
            scaler.update()
            if scaler.get_scale() < scale_before:
                logger.warning('AMP skipped an overflowing update and reduced its loss scale to %.0f.', scaler.get_scale())
            optimizer.zero_grad(set_to_none=True)
        total_loss += float(loss_sum.detach())
        total += len(labels)
        correct += int((logits.detach().argmax(1) == labels).sum())
        if (batch + 1) % config['log_every_batches'] == 0 or batch + 1 == len(loader):
            elapsed = time.perf_counter() - started
            eta = elapsed / (batch + 1) * (len(loader) - batch - 1)
            logger.info('batch %d/%d | weighted loss %.4f | accuracy %.3f | epoch ETA %.0fs',
                        batch + 1, len(loader), total_loss / total, correct / total, eta)
    return dict(loss=total_loss / total, accuracy=correct / total)


def train_candidate(name, config, manifest, root, run_dir, resume=None):
    ranking_space = config.get('ranking_score_space', 'probability')
    selection_metric = 'val_logit_margin_auc' if ranking_space == 'logit_margin' else 'val_roc_auc'
    if not resume:
        run_dir.mkdir(parents=True, exist_ok=False)
    logger = make_logger(run_dir)
    seed_everything(config['seed'])
    device = select_device()
    import torchvision
    environment = dict(python=platform.python_version(), torch=str(torch.__version__),
                       torchvision=str(torchvision.__version__), cuda_runtime=torch.version.cuda,
                       device=str(device), gpu=torch.cuda.get_device_name(device) if device.type == 'cuda' else None,
                       initialization='torchvision DEFAULT ImageNet weights')
    from importlib.metadata import version
    environment['packages'] = {package: version(package) for package in ('numpy', 'Pillow', 'scikit-learn')}
    code_root = Path(__file__).resolve().parent.parent
    code_files = ('src/training.py', 'src/modeling.py', 'src/scoring.py', 'src/data_protocol.py',
                  'src/prepare_dataset.py', 'scripts/train_models.py')
    environment['training_code_files'] = list(code_files)
    environment['training_code_sha256'] = hashlib.sha256(b'\0'.join(
        name.encode() + b'\0' + (code_root / name).read_bytes() for name in code_files)).hexdigest()
    amp = bool(config['mixed_precision'] and device.type == 'cuda')
    model = build_classifier(name, pretrained=resume is None).to(device)
    generator = torch.Generator().manual_seed(config['seed'])
    train_ds = ManifestDataset(manifest, root, 'train', image_transforms(
        config['image_size'], resize_mode=config['resize_mode'], training=True,
        augmentation_profile=config.get('augmentation_profile', 'standard')))
    val_ds = ManifestDataset(manifest, root, 'val', image_transforms(
        config['image_size'], resize_mode=config['resize_mode']))
    train_loader = DataLoader(train_ds, batch_size=config['batch_size'], shuffle=True,
                              num_workers=config['num_workers'], generator=generator, pin_memory=device.type == 'cuda')
    val_loader = DataLoader(val_ds, batch_size=config['batch_size'], shuffle=False,
                            num_workers=config['num_workers'], pin_memory=device.type == 'cuda')
    counts = Counter(train_ds.targets)
    weights = torch.tensor([len(train_ds) / (2 * counts[index]) for index in (0, 1)], dtype=torch.float32, device=device)
    head = list(model.classifier.parameters())
    head_ids = {id(parameter) for parameter in head}
    optimizer = torch.optim.AdamW([
        {'params': [parameter for parameter in model.parameters() if id(parameter) not in head_ids],
         'lr': config['backbone_learning_rate']},
        {'params': head, 'lr': config['head_learning_rate']},
    ], weight_decay=config['weight_decay'])
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=config['epochs'], eta_min=1e-6)
    scaler = torch.amp.GradScaler('cuda', enabled=amp)
    history, best, best_epoch, wait, start_epoch, best_val, stop_reference = [], -1.0, 0, 0, 1, None, -1.0
    if resume:
        state = torch.load(resume, map_location='cpu', weights_only=True)
        if state['manifest_sha256'] != manifest['manifest_sha256'] or state['config'] != config or state['architecture'] != name:
            raise ValueError('Resume requires the original config, architecture, and split manifest.')
        model.load_state_dict(state['model_state_dict'])
        optimizer.load_state_dict(state['optimizer'])
        scheduler.load_state_dict(state['scheduler'])
        scaler.load_state_dict(state['scaler'])
        history, best, best_epoch = state['history'], state['best_score'], state['best_epoch']
        wait, start_epoch, best_val = state['wait'], state['epoch'] + 1, state['best_validation']
        stop_reference = state['stop_reference']
        restore_rng(state['rng'], generator)
    write_json(config, run_dir / 'config.json')
    write_json(environment, run_dir / ('environment_resume.json' if resume else 'environment.json'))
    write_json(manifest, run_dir / 'split_manifest.json')
    logger.info('%s | device=%s | train=%d val=%d | batch=%d accumulation=%d | no test inference',
                name, device, len(train_ds), len(val_ds), config['batch_size'], config['accumulation_steps'])
    logger.info('Split manifest %s | checkpoints/logs: %s', manifest['manifest_sha256'], run_dir)
    if device.type == 'cuda':
        logger.info('GPU: %s | total VRAM %.1f GiB | mixed precision=%s',
                    torch.cuda.get_device_name(device), torch.cuda.get_device_properties(device).total_memory / 1024**3, amp)
    logger.info('Loss weights NORMAL=%.3f PNEUMONIA=%.3f | batch norm statistics frozen=%s',
                weights[0], weights[1], config['freeze_batch_norm'])
    started = time.perf_counter()
    try:
        for epoch in range(start_epoch, config['epochs'] + 1):
            if wait >= config['early_stopping_patience']:
                break
            epoch_start = time.perf_counter()
            head_only = epoch <= config['head_warmup_epochs']
            set_training_stage(model, head_only, config['freeze_batch_norm'])
            if device.type == 'cuda':
                torch.cuda.reset_peak_memory_stats(device)
            logger.info('Epoch %d/%d | %s', epoch, config['epochs'], 'classifier warm-up' if head_only else 'full fine-tuning')
            training = train_epoch(model, train_loader, optimizer, scaler, device, weights, config, logger)
            validation = validate(model, val_loader, device, amp)
            scheduler.step()
            row = dict(epoch=epoch, training=training,
                       validation={key: value for key, value in validation.items() if key not in {'targets', 'scores', 'margins'}},
                       seconds=round(time.perf_counter() - epoch_start, 2),
                       peak_vram_gib=torch.cuda.max_memory_allocated(device) / 1024**3 if device.type == 'cuda' else 0.0)
            history.append(row)
            score = validation['roc_auc_logit_margin'] if ranking_space == 'logit_margin' else validation['roc_auc']
            improved = score > best or (score == best and best_val is not None and validation['loss'] < best_val['loss'])
            if score > stop_reference + config['early_stopping_min_delta']:
                stop_reference, wait = score, 0
            elif not head_only:
                wait += 1
            if improved:
                best, best_epoch, best_val = score, epoch, validation
                payload = dict(model_state_dict={key: value.detach().cpu() for key, value in model.state_dict().items()},
                               architecture=name, class_names=list(CLASSES), class_to_idx={'NORMAL': 0, 'PNEUMONIA': 1},
                               image_size=config['image_size'], normalization=NORMALIZATION,
                               preprocessing={'resize_mode': config['resize_mode']}, best_epoch=epoch,
                               threshold=0.5, threshold_source='provisional; experiment not finalized',
                               selection_metric=selection_metric, selection_metric_value=score,
                               manifest_sha256=manifest['manifest_sha256'], training_config=config, environment=environment)
                atomic_save(payload, run_dir / 'best.pt')
                logger.info('New best validation AUC %.5f: best.pt', score)
            state = dict(model_state_dict={key: value.detach().cpu() for key, value in model.state_dict().items()},
                         architecture=name, config=config, manifest_sha256=manifest['manifest_sha256'], epoch=epoch,
                         optimizer=optimizer.state_dict(), scheduler=scheduler.state_dict(), scaler=scaler.state_dict(),
                         history=history, best_score=best, best_epoch=best_epoch, best_validation=best_val, wait=wait,
                         stop_reference=stop_reference,
                         environment=environment,
                         rng=rng_state(generator))
            atomic_save(state, run_dir / 'last.pt')
            write_json(history, run_dir / 'history.json')
            logger.info('Epoch %d | val loss %.4f | acc@0.5 %.3f | balanced acc %.3f | AUC %.5f | %.0fs | peak GPU %.2f GiB',
                        epoch, validation['loss'], validation['accuracy'], validation['balanced_accuracy'],
                        score, row['seconds'], row['peak_vram_gib'])
            if wait >= config['early_stopping_patience']:
                logger.info('Early stopping: no qualifying validation AUC improvement for %d fine-tuning epochs.', wait)
                break
    except DatasetIntegrityError as error:
        logger.error('Dataset integrity failure; training stopped. %s', error)
        logger.error('Completed epoch checkpoints are preserved. Verify/restore the original sources '
                     'before resuming; do not update hashes or skip the image to bypass this failure.')
        raise
    except KeyboardInterrupt:
        if (run_dir / 'last.pt').exists():
            logger.info('Interrupted. Resume the last completed epoch: --resume "%s"', run_dir / 'last.pt')
        else:
            logger.info('Interrupted before the first epoch checkpoint. Restart with a new run directory.')
        raise
    if best_val is None:
        raise ValueError('No completed validation checkpoint is available.')
    checkpoint = torch.load(run_dir / 'best.pt', map_location='cpu', weights_only=True)
    threshold_split = config.get('threshold_split', 'val')
    threshold_data = best_val
    if threshold_split == 'calibration':
        # No calibration inference occurs until model selection/early stopping have finished.
        model.load_state_dict(checkpoint['model_state_dict'])
        calibration_ds = ManifestDataset(manifest, root, 'calibration', image_transforms(
            config['image_size'], resize_mode=config['resize_mode']))
        calibration_loader = DataLoader(calibration_ds, batch_size=config['batch_size'], shuffle=False,
                                        num_workers=0, pin_memory=device.type == 'cuda')
        logger.info('Model selection finished. Reading %d separate threshold-calibration images once.', len(calibration_ds))
        threshold_data = validate(model, calibration_loader, device, amp)
    selected = choose_threshold(threshold_data['targets'], threshold_data['scores'], config['validation_min_sensitivity'])
    validation_selected = metrics(best_val['targets'], best_val['scores'], selected['threshold'])
    checkpoint.update(threshold=selected['threshold'], threshold_source=f'{threshold_split} only; maximize balanced accuracy subject to sensitivity target' if threshold_split == 'calibration' else 'validation only; maximize balanced accuracy subject to sensitivity target',
                      threshold_settings={'min_sensitivity': config['validation_min_sensitivity']},
                      threshold_split=threshold_split, validation_metrics=validation_selected, finalized=True)
    if threshold_split == 'calibration':
        checkpoint['calibration_metrics'] = selected
    atomic_save(checkpoint, run_dir / 'best.pt')
    summary = dict(architecture=name, best_epoch=best_epoch, selection_metric=selection_metric, selection_metric_value=best,
                   validation_loss=best_val['loss'], validation_at_0_5=metrics(best_val['targets'], best_val['scores']),
                   validation_at_selected_threshold=validation_selected, manifest_sha256=manifest['manifest_sha256'],
                   checkpoint=(run_dir / 'best.pt').relative_to(ROOT).as_posix(),
                   checkpoint_sha256=hashlib.sha256((run_dir / 'best.pt').read_bytes()).hexdigest(),
                   elapsed_seconds=round(time.perf_counter() - started, 2), test_evaluated=False)
    summary['threshold_split'] = threshold_split
    if threshold_split == 'calibration':
        summary['calibration_at_selected_threshold'] = selected
        write_json(dict(targets=threshold_data['targets'], scores=threshold_data['scores']), run_dir / 'calibration_predictions.json')
        write_json(dict(metrics=selected, loss=threshold_data['loss'], manifest_sha256=manifest['manifest_sha256'],
                        threshold_split='calibration', caveat='Threshold holdout only; no probability calibration or clinical validity established.'),
                   run_dir / 'calibration_summary.json')
    write_json(dict(targets=best_val['targets'], scores=best_val['scores'], logit_margins=best_val.get('margins')),
               run_dir / 'validation_predictions.json')
    write_json(summary, run_dir / 'validation_summary.json')
    logger.info('Finished: best epoch=%d | validation AUC=%.5f | %s threshold=%.5f | threshold-holdout balanced acc=%.3f sensitivity=%.3f specificity=%.3f',
                best_epoch, best, threshold_split, selected['threshold'], selected['balanced_accuracy'], selected['sensitivity'], selected['specificity'])
    logger.info('Test set remains unevaluated. Current API checkpoint has not changed.')
    return summary
