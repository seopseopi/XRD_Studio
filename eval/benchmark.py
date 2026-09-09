"""Reproducible image-to-numeric benchmark; GT is used only after inference."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import subprocess
import time
from pathlib import Path

import numpy as np
from scipy.signal import find_peaks

from core.io import load_image, load_manual_inputs
from eval.metrics import _numeric_y_mae_norm
from runner.run_simple import run_simple_pipeline


def measure(result, gt):
    x = np.asarray(gt['x_values'], dtype=float)
    y = np.asarray(gt['y_values'], dtype=float)
    px = np.asarray(result['two_theta_values'], dtype=float)
    py = np.asarray(result['intensities'], dtype=float)
    if len(px) < 2 or not np.all(np.isfinite(py)):
        raise ValueError('Empty or non-finite prediction')
    scale = float(np.ptp(y))
    # Identical prominence rule on GT and predicted numeric curves.
    gi, _ = find_peaks(y, prominence=0.05 * scale)
    pi, _ = find_peaks(py, prominence=0.05 * scale)
    pairs = sorted((abs(x[g] - px[p]), int(g), int(p)) for g in gi for p in pi)
    used_g, used_p = set(), set()
    for distance, g, p in pairs:
        if distance <= 0.2 and g not in used_g and p not in used_p:
            used_g.add(g)
            used_p.add(p)
    return {
        'mae_norm': _numeric_y_mae_norm(result, gt),
        'range_ratio': float(np.ptp(py) / scale),
        'peak_precision': len(used_p) / len(pi) if len(pi) else None,
        'peak_recall': len(used_g) / len(gi) if len(gi) else None,
        'gt_peak_count': len(gi), 'pred_peak_count': len(pi),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, default=Path('data/test_canonical_30/manifest.csv'))
    p.add_argument('--data-root', type=Path, default=Path('.'), help='Root for manifest-relative paths')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--engine', choices=['simple', 'classic'], default='simple')
    p.add_argument('--repeat', type=int, default=3)
    p.add_argument('--limit', type=int)
    p.add_argument('--label', default='working-tree')
    args = p.parse_args()
    if args.repeat < 1:
        p.error('--repeat must be positive')
    entries = list(csv.DictReader(args.manifest.open(encoding='utf-8-sig')))
    if args.limit:
        entries = entries[:args.limit]
    if args.engine == 'classic':
        from runner.run_local import run_pipeline
    cases = []
    for entry in entries:
        paths = {k: args.data_root / entry[k] for k in ('input_image', 'mi_json', 'gt_json')}
        hashes = {k: hashlib.sha256(v.read_bytes()).hexdigest() for k, v in paths.items()}
        for k, digest in hashes.items():
            expected = entry.get('sha256_' + k)
            if expected and expected != digest:
                raise ValueError(f"Input hash mismatch: {entry['test_id']} {k}")
        image, mi = load_image(str(paths['input_image'])), load_manual_inputs(str(paths['mi_json']))
        times = []
        for _ in range(args.repeat):
            start = time.perf_counter()
            result = (run_simple_pipeline(image, mi) if args.engine == 'simple'
                      else run_pipeline(image, mi, roi_upscale_factor=2)[0])
            times.append(time.perf_counter() - start)
        prediction = result.to_dict()
        gt = json.loads(paths['gt_json'].read_text())
        row = {'test_id': entry['test_id'], 'sample_id': entry['sample_id'],
               'domain': entry['domain'], 'sha256': hashes,
               **measure(prediction, gt), 'seconds_median': float(np.median(times)),
               'seconds_runs': times, 'prediction': prediction}
        cases.append(row)
        print(f"{row['test_id']}: MAE={row['mae_norm']:.6f} time={row['seconds_median']:.4f}s", flush=True)
    summary = {}
    for domain in ['all'] + sorted({r['domain'] for r in cases}):
        group = [r for r in cases if domain == 'all' or r['domain'] == domain]
        summary[domain] = {'n': len(group)}
        for key in ['mae_norm', 'range_ratio', 'seconds_median', 'peak_precision', 'peak_recall']:
            values = [r[key] for r in group if r[key] is not None]
            summary[domain][key + '_mean'] = float(np.mean(values)) if values else None
    report = {
        'label': args.label, 'engine': args.engine, 'repeat': args.repeat,
        'revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'environment': {'python': platform.python_version(), 'platform': platform.platform(), 'numpy': np.__version__},
        'protocol': 'In-process inference, preloaded RGB image, median of repeats; excludes imports, image I/O and HTTP. MAE on full GT x-grid with endpoint interpolation / GT range. Peaks: 5% GT-range prominence, one-to-one matching within 0.2 degrees. GT never passed to inference.',
        'summary': summary, 'cases': cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
