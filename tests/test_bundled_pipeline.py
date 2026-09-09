"""The default web subprocess must execute the same implementation as the CLI."""
from pathlib import Path

import numpy as np

from core.io import load_image, load_manual_inputs
from runner.run_simple import run_simple_pipeline


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'web/server/analysis/python/xrd_digitizer'


def test_bundled_core_matches_root():
    for name in ['preprocess/simple_trace.py', 'calibrate/axis_mapping.py',
                 'calibrate/numeric_export.py', 'runner/run_simple.py',
                 'preprocess/auto_detect.py', 'runner/run_detect.py']:
        assert (ROOT / name).read_text() == (BUNDLE / name).read_text(), name


def test_sample_pipeline_returns_finite_calibrated_curve():
    result = run_simple_pipeline(load_image(str(ROOT / 'examples/sample.png')),
                                 load_manual_inputs(str(ROOT / 'examples/sample_mi.json')))
    assert len(result.two_theta_values) == len(result.intensities) > 100
    assert np.all(np.isfinite(result.intensities))
    assert np.all(np.diff(result.two_theta_values) > 0)
    assert len(result.peaks_numeric_curve) > 0
    assert result.model_assist['trace_method'] == 'topmost'
