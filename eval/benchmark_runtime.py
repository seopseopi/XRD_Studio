"""Measure resampling and alternating fresh CLI processes against a checkout."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
from calibrate.numeric_export import resample_two_theta_uniform


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline-dir', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, default=Path('outputs/performance'))
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    baseline = args.baseline_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location('baseline_export', baseline/'calibrate/numeric_export.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tt = np.linspace(5, 75, 950).tolist()
    yy = np.random.default_rng(2).random(950).tolist()
    expected = module.resample_two_theta_uniform(tt, yy, 5, 75, 20000)
    actual = resample_two_theta_uniform(tt, yy, 5, 75, 20000)
    if actual != expected:
        raise ValueError('Resampling output differs from baseline')
    timings = {'before': [], 'after': []}
    for _ in range(10):
        for label, fn in [('before', module.resample_two_theta_uniform), ('after', resample_two_theta_uniform)]:
            start = time.perf_counter()
            fn(tt, yy, 5, 75, 20000)
            timings[label].append(time.perf_counter()-start)
    (args.output_dir/'resample.json').write_text(json.dumps(timings, indent=2)+'\n')
    cold = {'before': [], 'after': []}
    command = [sys.executable, '-m', 'runner.run_simple', '--image_path', str(root/'examples/sample.png'),
               '--manual_inputs_path', str(root/'examples/sample_mi.json'), '--stdout']
    for index in range(7):
        order = [('before', baseline), ('after', root)]
        for label, cwd in order if index % 2 == 0 else reversed(order):
            start = time.perf_counter()
            subprocess.run(command, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
            cold[label].append(time.perf_counter()-start)
    (args.output_dir/'cold_comparison.json').write_text(json.dumps(cold, indent=2)+'\n')
    print(json.dumps({'resample_median': {k:float(np.median(v)) for k,v in timings.items()},
                      'cold_cli_median': {k:float(np.median(v)) for k,v in cold.items()}}, indent=2))


if __name__ == '__main__':
    main()
