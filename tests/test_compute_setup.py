"""Exercise dependency selection and failure recovery without running pip or a server."""

import subprocess
from unittest.mock import Mock

import pytest
import torch

from scripts import setup_compute as setup
from src import compute


def gpu(capability='7.5', driver='621.14', memory=4096):
    return dict(index=0, name='test GPU', capability=capability, driver=driver, memory_mib=memory)


@pytest.mark.parametrize('gpus,expected', [
    ([], setup.CPU),
    ([gpu()], setup.CUDA126),
    ([gpu('8.9')], setup.CUDA126),
    ([gpu('12.0')], setup.CUDA130),
    ([gpu('10.0')], setup.CUDA130),
    ([gpu(driver='500.00')], setup.CPU),
    ([gpu(memory=2048)], setup.CPU),
    ([gpu('6.1')], setup.CPU),
    ([gpu('99.0')], setup.CPU),
])
def test_profile_selection(gpus, expected):
    assert setup.choose_profile(gpus, system='Windows')[0] == expected


def test_explicit_cpu_and_strict_cuda():
    assert setup.choose_profile([gpu()], 'cpu')[0] == setup.CPU
    with pytest.raises(RuntimeError, match='explicitly requested'):
        setup.choose_profile([], 'cuda')


def test_driver_cutoffs_are_platform_specific():
    assert setup.choose_profile([gpu(driver='560.75')], system='Windows')[0] == setup.CPU
    assert setup.choose_profile([gpu(driver='560.76')], system='Windows')[0] == setup.CUDA126
    assert setup.choose_profile([gpu(driver='560.28.03')], system='Linux')[0] == setup.CUDA126
    assert setup.choose_profile([gpu('12.0', driver='580.87')], system='Windows')[0] == setup.CPU


def test_existing_cpu_build_is_replaced_by_an_explicit_cuda_build():
    assert setup.CUDA126.packages == ['torch==2.14.1+cu126', 'torchvision==0.29.1+cu126']


@pytest.mark.parametrize('profile', [setup.CPU, setup.CUDA126, setup.CUDA130])
def test_shared_dependency_install_preserves_selected_profile(monkeypatch, profile, capsys):
    pip = Mock()
    monkeypatch.setattr(setup, 'pip', pip)
    monkeypatch.setattr(setup, 'verify', Mock())
    assert setup.install(profile, 'auto') == profile
    assert pip.call_args_list[1].args == (
        'install', '-r', 'requirements.txt', '-c', 'constraints-local.txt',
        '-c', str(profile.requirements_path),
    )
    assert 'requirements.txt' in capsys.readouterr().out


def test_auto_restores_cpu_when_cuda_execution_fails(monkeypatch):
    pip = Mock()
    verify = Mock(side_effect=[subprocess.CalledProcessError(1, 'probe'), None, None])
    monkeypatch.setattr(setup, 'pip', pip)
    monkeypatch.setattr(setup, 'verify', verify)
    assert setup.install(setup.CUDA126, 'auto') == setup.CPU
    assert pip.call_args_list[1].args[1:3] == tuple(setup.CPU.packages)
    assert verify.call_args_list[-1].args == (setup.CPU,)


def test_strict_cuda_reports_failure_without_silently_switching(monkeypatch):
    pip = Mock(side_effect=subprocess.CalledProcessError(1, 'pip'))
    monkeypatch.setattr(setup, 'pip', pip)
    with pytest.raises(subprocess.CalledProcessError):
        setup.install(setup.CUDA126, 'cuda')
    assert pip.call_count == 1


def test_gpu_query_failure_is_reported_as_cpu_plan(monkeypatch):
    monkeypatch.setattr(setup.shutil, 'which', lambda _: 'nvidia-smi')
    monkeypatch.setattr(setup.subprocess, 'run', Mock(side_effect=subprocess.TimeoutExpired('nvidia-smi', 15)))
    gpus, message = setup.inspect_gpus()
    assert gpus == []
    assert 'inspection failed' in message


def test_gpu_query_parses_multiple_cards(monkeypatch):
    monkeypatch.setattr(setup.shutil, 'which', lambda _: 'nvidia-smi')
    monkeypatch.setattr(setup.subprocess, 'run', Mock(return_value=Mock(
        stdout='0, GTX 1650, 4096, 7.5, 621.14\n1, RTX 5090, 32768, 12.0, 621.14\n')))
    gpus, _ = setup.inspect_gpus()
    assert len(gpus) == 2
    assert setup.choose_profile(gpus, system='Windows')[0] == setup.CUDA130


def test_default_setup_only_plans_and_never_runs_pip(monkeypatch, capsys):
    monkeypatch.setattr(setup, 'inspect_gpus', lambda: ([gpu()], 'Detected test GPU'))
    install = Mock(side_effect=AssertionError('Must not install'))
    monkeypatch.setattr(setup, 'install', install)
    assert setup.main([]) == 0
    assert 'Read-only plan' in capsys.readouterr().out
    install.assert_not_called()


def test_installer_refuses_global_python(monkeypatch):
    monkeypatch.setattr(setup.sys, 'prefix', str(setup.ROOT / 'not-the-project-venv'))
    install = Mock()
    monkeypatch.setattr(setup, 'install', install)
    with pytest.raises(SystemExit) as error:
        setup.main(['--install'])
    assert error.value.code == 2
    install.assert_not_called()


def test_cpu_preference_does_not_probe_gpu(monkeypatch):
    available = Mock(side_effect=AssertionError('Must not probe'))
    monkeypatch.setattr(torch.cuda, 'is_available', available)
    assert compute.select_device('cpu').type == 'cpu'
    available.assert_not_called()


def test_auto_falls_back_when_cuda_is_absent(monkeypatch):
    monkeypatch.setattr(torch.cuda, 'is_available', lambda: False)
    assert compute.select_device('auto').type == 'cpu'
    with pytest.raises(RuntimeError, match='explicitly requested'):
        compute.select_device('cuda')


def test_auto_tries_another_gpu_if_the_first_cannot_execute(monkeypatch):
    monkeypatch.setattr(torch.cuda, 'is_available', lambda: True)
    monkeypatch.setattr(torch.cuda, 'device_count', lambda: 2)
    monkeypatch.setattr(torch.cuda, 'get_device_name', lambda _: 'working GPU')
    monkeypatch.setattr(compute, '_probe_cuda', Mock(side_effect=[
        RuntimeError('no kernel image'), torch.device('cuda:1'),
    ]))
    assert str(compute.select_device('auto')) == 'cuda:1'


def test_visible_but_broken_cuda_uses_cpu(monkeypatch):
    monkeypatch.setattr(torch.cuda, 'is_available', lambda: True)
    monkeypatch.setattr(torch.cuda, 'device_count', lambda: 1)
    monkeypatch.setattr(compute, '_probe_cuda', Mock(side_effect=RuntimeError('driver initialization failed')))
    assert compute.select_device('auto').type == 'cpu'


def test_invalid_device_setting_is_not_silently_ignored():
    with pytest.raises(ValueError, match='auto, cpu, or cuda'):
        compute.select_device('cdua')


@pytest.mark.parametrize('preference,raises', [('auto', False), ('cuda', True)])
def test_model_cuda_initialization_failure_obeys_preference(tmp_path, monkeypatch, preference, raises):
    from src.api import model_service

    class TinyModel(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.classifier = torch.nn.Linear(3, 2)

        def to(self, device):
            if device.type == 'cuda':
                raise RuntimeError('GPU allocation failed')
            return self

    checkpoint = tmp_path / 'model.pth'
    torch.save({'model_state_dict': TinyModel().state_dict()}, checkpoint)
    monkeypatch.setenv('PULMOSCAN_DEVICE', preference)
    monkeypatch.setattr(model_service, 'select_device', lambda: torch.device('cuda:0'))
    monkeypatch.setattr(model_service.models, 'densenet121', lambda **_: TinyModel())
    if raises:
        with pytest.raises(RuntimeError, match='GPU allocation failed'):
            model_service.DenseNetInferenceEngine(checkpoint)
    else:
        assert model_service.DenseNetInferenceEngine(checkpoint).device.type == 'cpu'
