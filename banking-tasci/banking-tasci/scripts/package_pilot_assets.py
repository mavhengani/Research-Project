#!/usr/bin/env python3
"""Package verified pilot inputs without copying a macOS environment."""
import hashlib
import io
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
REVISION = '86b5e0934494bd15c9632b12f734a8a67f723594'
EXPECTED = '5ea719ec528510ddd8566410a1b533ff294093c2ce87538f472dae789cf9e3ea'


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def main():
    corpus = ROOT / 'data/processed/new_pipeline_v1/strict_unlabelled.jsonl'
    if sha(corpus) != EXPECTED:
        raise ValueError('PROTECTED_ARTIFACT_MISMATCH')
    paths = [corpus]
    for directory in (
        'artifacts/manifests/new_pipeline_v1/strict_unlabelled',
        'artifacts/manifests/new_pipeline_v1/mlm',
        f'.cache/huggingface/hub/models--bert-base-uncased/snapshots/{REVISION}',
    ):
        folder = ROOT / directory
        if not folder.is_dir():
            raise FileNotFoundError(folder)
        paths.extend(path for path in folder.rglob('*') if path.is_file())
    paths = sorted(set(paths))
    checksums = ''.join(f'{sha(path)}  {path.relative_to(ROOT)}\n' for path in paths)
    destination = ROOT / 'outputs/cluster_staging/pilot_assets_20261020.tar'
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as handle:
        with tarfile.open(fileobj=handle, mode='w', dereference=True) as archive:
            for path in paths:
                archive.add(path, arcname=str(path.relative_to(ROOT)), recursive=False)
            content = checksums.encode()
            info = tarfile.TarInfo('pilot_assets.sha256')
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    checksum = sha(destination)
    destination.with_suffix('.tar.sha256').write_text(f'{checksum}  {destination.name}\n')
    print(json.dumps({'archive': str(destination), 'sha256': checksum, 'files': len(paths), 'bytes': destination.stat().st_size}, indent=2))


if __name__ == '__main__':
    main()
