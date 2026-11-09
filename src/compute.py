"""Select a working compute device without installing packages or starting services."""

import logging
import os

import torch

logger = logging.getLogger(__name__)


def device_preference(value=None):
    preference = (value or os.getenv('PULMOSCAN_DEVICE', 'auto')).strip().lower()
    if preference not in {'auto', 'cpu', 'cuda'}:
        raise ValueError('PULMOSCAN_DEVICE must be auto, cpu, or cuda.')
    return preference


def _probe_cuda(index):
    """Actually execute a kernel: driver visibility alone is not sufficient."""
    device = torch.device(f'cuda:{index}')
    with torch.inference_mode():
        sample = torch.ones((16, 16), device=device)
        sample @ sample
        torch.cuda.synchronize(device)
    return device


def select_device(preference=None):
    preference = device_preference(preference)
    if preference == 'cpu':
        logger.info('Compute device: cpu (explicit selection).')
        return torch.device('cpu')

    failures = []
    try:
        if torch.cuda.is_available():
            for index in range(torch.cuda.device_count()):
                try:
                    device = _probe_cuda(index)
                    logger.info('Compute device: %s (%s).', device, torch.cuda.get_device_name(index))
                    return device
                except (RuntimeError, AssertionError) as error:
                    failures.append(f'CUDA device {index}: {error}')
        else:
            failures.append('CUDA is unavailable in this PyTorch installation or driver')
    except (RuntimeError, AssertionError) as error:
        failures.append(str(error))

    reason = '; '.join(failures) or 'No visible CUDA devices'
    if preference == 'cuda':
        raise RuntimeError(f'CUDA was explicitly requested but is not usable: {reason}')
    logger.warning('Compute device: cpu. %s. Run scripts/setup_compute.py to check dependencies.', reason)
    return torch.device('cpu')
