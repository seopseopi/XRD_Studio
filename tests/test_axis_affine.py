import pytest

from calibrate.axis_mapping import build_x_mapping, build_y_mapping, pixel_x_to_value, pixel_y_to_value


@pytest.mark.parametrize('points,values', [([[30, 80], [110, 80]], [10, 90]), ([[110, 80], [30, 80]], [10, 90]), ([[30, 80], [110, 80]], [1e6, 1e6+0.1])])
def test_x_calibration_hits_both_anchors(points, values):
    mapping = build_x_mapping(points, values, [20, 10, 120, 90])
    for point, value in zip(points, values):
        assert pixel_x_to_value(point[0]-20, mapping) == pytest.approx(value)


def test_y_inversion_and_degenerate_axis():
    mapping = build_y_mapping([[20, 90], [20, 10]], [-5, 95], [20, 10, 120, 90])
    assert pixel_y_to_value(40, mapping) == pytest.approx(45)
    flat = build_x_mapping([[20, 90], [20, 10]], [7, 9], [20, 10, 120, 90])
    assert pixel_x_to_value(20, flat) == 7
