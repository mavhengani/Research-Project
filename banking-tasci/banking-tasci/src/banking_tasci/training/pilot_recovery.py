"""Atomic, checksummed pilot recovery state, saved at update boundaries."""
import hashlib
import json
import os
import random
import shutil
import tempfile
from pathlib import Path

import torch


def digest(path):
    checksum = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            checksum.update(chunk)
    return checksum.hexdigest()


def save_recovery(path, model, optimizer, scheduler, metadata, progress):
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    temporary = Path(tempfile.mkdtemp(prefix='.checkpoint-', dir=path.parent))
    try:
        torch.save(model.state_dict(), temporary / 'model_state.pt')
        torch.save(optimizer.state_dict(), temporary / 'optimizer_state.pt')
        torch.save({
            'scheduler': scheduler.state_dict(),
            'python_rng': random.getstate(),
            'torch_rng': torch.get_rng_state(),
            'cuda_rng': torch.cuda.get_rng_state_all() if torch.cuda.is_available() else [],
            'progress': progress,
        }, temporary / 'recovery_state.pt')
        (temporary / 'checkpoint_metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
        checksums = {file.name: digest(file) for file in temporary.iterdir()}
        (temporary / 'checksums.json').write_text(json.dumps(checksums, indent=2) + '\n')
        os.rename(temporary, path)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def load_recovery(path, model, optimizer, scheduler, expected):
    from .self_supervised_checkpoint import validate_checkpoint_metadata
    path = Path(path)
    required = {'model_state.pt', 'optimizer_state.pt', 'recovery_state.pt', 'checkpoint_metadata.json'}
    checksums = json.loads((path / 'checksums.json').read_text())
    if set(checksums) != required:
        raise ValueError('INCOMPLETE_RECOVERY_CHECKPOINT')
    for name, checksum in checksums.items():
        if digest(path / name) != checksum:
            raise ValueError('RECOVERY_CHECKSUM_MISMATCH:' + name)
    actual = json.loads((path / 'checkpoint_metadata.json').read_text())
    validate_checkpoint_metadata(expected, actual, resume=True)
    if actual.get('pilot_policy') != expected.get('pilot_policy'):
        raise ValueError('RESUME_PILOT_POLICY_MISMATCH')
    model.load_state_dict(torch.load(path / 'model_state.pt', map_location='cpu', weights_only=True))
    optimizer.load_state_dict(torch.load(path / 'optimizer_state.pt', map_location='cpu', weights_only=True))
    state = torch.load(path / 'recovery_state.pt', map_location='cpu', weights_only=True)
    scheduler.load_state_dict(state['scheduler'])
    random.setstate(state['python_rng'])
    torch.set_rng_state(state['torch_rng'])
    if state['cuda_rng']:
        if not torch.cuda.is_available():
            raise ValueError('RESUME_CUDA_DEVICE_REQUIRED')
        torch.cuda.set_rng_state_all(state['cuda_rng'])
    return state['progress']
