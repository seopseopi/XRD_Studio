"""Small images isolate sampling, border masking and subpixel extraction."""
import numpy as np
import pytest

from preprocess.simple_trace import adaptive_max_dist, extract_curve_simple, sample_curve_rgb


@pytest.mark.parametrize('background,foreground', [(255, 20), (10, 240), (255, 225)])
def test_sample_is_foreground_not_patch_average(background, foreground):
    roi = np.full((60, 60, 3), background, dtype=np.uint8)
    roi[30, 25:36] = foreground
    color = sample_curve_rgb(roi, (130, 230), (100, 200, 160, 260))
    assert color == (foreground,) * 3
    threshold = adaptive_max_dist(color, (background,) * 3)
    assert 0 < threshold < np.sqrt(3) * abs(background - foreground)


def test_argmin_respects_removed_axis_rows():
    roi = np.full((40, 20, 3), 255, dtype=np.uint8)
    roi[0, :] = 0  # perfect target match, but a frame
    roi[20, 4:16] = 20
    trace = extract_curve_simple(roi, (0, 0, 0), max_dist=80, method='argmin')
    assert trace[10] == 20
    assert trace[2] is None


def test_antialias_crossing_and_missing_columns():
    roi = np.full((30, 20, 3), 255, dtype=np.uint8)
    roi[10, 4:16] = 120
    roi[11:13, 4:16] = 0
    threshold = 60 * np.sqrt(3)
    trace = extract_curve_simple(roi, (0, 0, 0), threshold, method='topmost')
    assert trace[8] == pytest.approx(10.5)
    assert trace[0] is None


def test_empty_and_invalid_method():
    assert extract_curve_simple(np.zeros((0, 4, 3)), (0, 0, 0)) == [None] * 4
    with pytest.raises(ValueError, match='method'):
        extract_curve_simple(np.zeros((2, 2, 3)), (0, 0, 0), method='typo')


def test_centerline_avoids_upper_edge_bias_and_restores_narrow_apex():
    roi = np.full((100, 80, 3), 255, dtype=np.uint8)
    for x in range(5, 75):
        y = 65 + x // 10
        roi[y-2:y+3, x] = 20
    roi[15:72, 40] = 20  # one unresolved sharp diffraction peak
    center = extract_curve_simple(roi, (20, 20, 20), method='centerline')
    top = extract_curve_simple(roi, (20, 20, 20), method='topmost')
    assert center[20] == pytest.approx(67)
    assert top[20] < center[20] - 1
    assert center[40] == pytest.approx(top[40])


def test_colored_curve_excludes_gray_grid_ink():
    roi = np.full((80, 80, 3), 250, dtype=np.uint8)
    roi[15, 5:75] = 135  # falls inside a simple RGB distance ball
    roi[55, 5:75] = [35, 95, 180]
    trace = extract_curve_simple(roi, (35, 95, 180), max_dist=170)
    assert 54 < trace[40] <= 55
