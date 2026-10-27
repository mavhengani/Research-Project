import sys
from pathlib import Path
import random

import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from banking_tasci.training.pilot_recovery import save_recovery, load_recovery
from banking_tasci.training.self_supervised_checkpoint import COMMON_FIELDS


def setup_training():
    model = torch.nn.Sequential(torch.nn.Linear(3, 3), torch.nn.Dropout(.2))
    optimizer = torch.optim.AdamW(model.parameters(), lr=.01)
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, 1, .9)
    return model, optimizer, scheduler


def step(model, optimizer, scheduler):
    optimizer.zero_grad()
    loss = model(torch.rand(2, 3)).square().mean()
    loss.backward()
    optimizer.step()
    scheduler.step()


def test_resume_matches_uninterrupted_next_update(tmp_path):
    torch.manual_seed(42)
    random.seed(42)
    model, optimizer, scheduler = setup_training()
    step(model, optimizer, scheduler)
    metadata = dict.fromkeys(COMMON_FIELDS, 'test')
    metadata['pilot_policy'] = {'updates': 3}
    path = tmp_path / 'checkpoint-1'
    save_recovery(path, model, optimizer, scheduler, metadata, {'next_offset': 32})
    step(model, optimizer, scheduler)
    expected = {key: value.clone() for key, value in model.state_dict().items()}
    expected_random = random.random()
    restored, opt, sched = setup_training()
    progress = load_recovery(path, restored, opt, sched, metadata)
    assert progress['next_offset'] == 32
    step(restored, opt, sched)
    assert all(torch.equal(expected[key], value) for key, value in restored.state_dict().items())
    assert sched.state_dict() == scheduler.state_dict()
    assert random.random() == expected_random


def test_corrupt_checkpoint_rejected_before_loading(tmp_path):
    model, optimizer, scheduler = setup_training()
    metadata = dict.fromkeys(COMMON_FIELDS, 'test')
    path = tmp_path / 'checkpoint-1'
    save_recovery(path, model, optimizer, scheduler, metadata, {})
    (path / 'model_state.pt').write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='RECOVERY_CHECKSUM_MISMATCH'):
        load_recovery(path, model, optimizer, scheduler, metadata)
