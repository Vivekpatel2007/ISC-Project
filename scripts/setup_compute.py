"""Hardware-aware PyTorch installation. Default is read-only; --install changes this venv."""

import argparse
import csv
from dataclasses import dataclass
import io
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class Profile:
    name: str

    @property
    def requirements_path(self):
        return ROOT / 'requirements' / f'compute-{self.name}.txt'

    @property
    def packages(self):
        return [line.strip() for line in self.requirements_path.read_text(encoding='utf-8').splitlines()
                if line.strip() and not line.lstrip().startswith('#')]

    @property
    def index(self):
        return f'https://download.pytorch.org/whl/{self.name}'


CPU = Profile('cpu')
CUDA126 = Profile('cu126')
CUDA130 = Profile('cu130')
LEGACY_CAPABILITIES = {'7.5', '8.0', '8.6', '8.9', '9.0'}
BLACKWELL_CAPABILITIES = {'10.0', '12.0'}


def inspect_gpus():
    executable = shutil.which('nvidia-smi')
    if not executable and platform.system() == 'Windows':
        candidate = Path('C:/Windows/System32/nvidia-smi.exe')
        if candidate.is_file():
            executable = str(candidate)
    if not executable:
        return [], 'nvidia-smi is unavailable; no NVIDIA driver was detected.'
    try:
        result = subprocess.run(
            [executable, '--query-gpu=index,name,memory.total,compute_cap,driver_version',
             '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=15, check=True,
        )
        rows = []
        for row in csv.reader(io.StringIO(result.stdout), skipinitialspace=True):
            if len(row) != 5:
                raise ValueError('Unexpected GPU query response')
            index, name, memory, capability, driver = (item.strip() for item in row)
            version_tuple(driver)
            rows.append(dict(index=int(index), name=name, memory_mib=int(memory),
                             capability=capability, driver=driver))
        return rows, 'NVIDIA hardware inspected without importing PyTorch.'
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return [], f'NVIDIA inspection failed ({type(error).__name__}); use CPU or repair the driver.'


def version_tuple(value):
    return tuple(int(part) for part in value.split('.'))


def choose_profile(gpus, requested='auto', system=None):
    if requested == 'cpu':
        return CPU, 'CPU explicitly selected.'
    system = system or platform.system()
    for gpu in sorted(gpus, key=lambda item: item['memory_mib'], reverse=True):
        if gpu['memory_mib'] < 4096:
            continue
        capability = gpu['capability']
        if capability in LEGACY_CAPABILITIES:
            profile = CUDA126
            minimum = '560.76' if system == 'Windows' else '560.28.03'
        elif capability in BLACKWELL_CAPABILITIES:
            profile = CUDA130
            minimum = '580.88' if system == 'Windows' else '580.65.06'
        else:
            continue
        if version_tuple(gpu['driver']) >= version_tuple(minimum):
            return profile, f"{gpu['name']} qualifies for {profile.name} (driver {gpu['driver']})."
    reason = 'No GPU meets the documented architecture, 4 GB VRAM, and driver requirements.'
    if requested == 'cuda':
        raise RuntimeError(f'{reason} CUDA was explicitly requested; no packages were changed.')
    return CPU, reason


def pip(*arguments):
    subprocess.run([sys.executable, '-m', 'pip', *arguments], cwd=ROOT, check=True)


def verify(profile):
    # A fresh interpreter is essential after replacing native wheels.
    code = (
        'import torch, torchvision; from src.compute import select_device; '
        f'device = select_device({"cpu" if profile == CPU else "cuda"!r}); '
        'print(f"Verified: torch={torch.__version__}, torchvision={torchvision.__version__}, device={device}")'
    )
    subprocess.run([sys.executable, '-c', code], cwd=ROOT, check=True, timeout=120)


def install(profile, requested):
    try:
        pip('install', *profile.packages, '--index-url', profile.index)
        verify(profile)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        if profile == CPU or requested == 'cuda':
            raise
        print('CUDA installation or execution failed. Restoring the CPU profile.', flush=True)
        profile = CPU
        pip('install', *profile.packages, '--index-url', profile.index)
        verify(profile)

    # The shared requirements contain no hardware-dependent torch replacement.
    # Retain the selected profile as constraints for any transitive torch requirement.
    print('Installing shared Python dependencies from requirements.txt ...', flush=True)
    pip('install', '-r', 'requirements.txt', '-c', 'constraints-local.txt', '-c', str(profile.requirements_path))
    pip('check')
    verify(profile)
    return profile


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', choices=['auto', 'cpu', 'cuda'], default='auto')
    parser.add_argument('--install', action='store_true', help='Install into the active project .venv')
    parser.add_argument('--check', action='store_true', help='Also report the currently installed compute device')
    args = parser.parse_args(argv)
    if platform.system() not in {'Windows', 'Linux'} or platform.machine().lower() not in {'amd64', 'x86_64'}:
        parser.error('This installer supports Windows/Linux x86-64; see README.md for platform limits.')
    if sys.version_info[:2] != (3, 11):
        parser.error('Use the documented Python 3.11 environment for these pinned profiles.')
    if args.install and Path(sys.prefix).resolve() != (ROOT / '.venv').resolve():
        parser.error('Run with the project .venv interpreter. Global Python is never modified.')

    gpus, message = inspect_gpus()
    print(message, flush=True)
    for gpu in gpus:
        print(f"GPU {gpu['index']}: {gpu['name']}; {gpu['memory_mib']} MiB; "
              f"CC {gpu['capability']}; driver {gpu['driver']}", flush=True)
    try:
        profile, reason = choose_profile(gpus, args.device)
        print(f'Selected dependency profile: {profile.name}. {reason}', flush=True)
        print('Packages: ' + ', '.join(profile.packages), flush=True)
        if args.install:
            profile = install(profile, args.device)
            print(f'Installation complete: {profile.name}. No server was started.', flush=True)
        else:
            print('Read-only plan. Add --install to apply it. No packages were changed.', flush=True)
        if args.check:
            subprocess.run([sys.executable, str(ROOT / 'scripts/check_compute.py')], cwd=ROOT, check=True, timeout=120)
        return 0
    except (RuntimeError, subprocess.SubprocessError) as error:
        print(f'Compute setup failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
