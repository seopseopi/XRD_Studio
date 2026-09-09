"""
Simple pixel-based curve extraction.

깨끗한 이미지(흰/단색 배경 + 단일 색상의 얇은 곡선) 전용 trace 추출.
classical 파이프라인의 candidate building / DP trace 등을 우회한다.

각 ROI 컬럼에서 곡선 색상과 맞는 픽셀을 찾아 sub-pixel y를 반환한다.
기본값은 상단 AA 경계이며, 중심선 추출은 선택적으로 사용할 수 있다.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np


def extract_curve_simple(
    roi: np.ndarray,
    curve_rgb: Tuple[int, int, int],
    max_dist: float = 80.0,
    method: str = 'topmost',
) -> List[Optional[float]]:
    """
    각 컬럼에서 curve y를 반환.

    method:
      'centerline'              - 선택. 가중 중심선 + 고립된 좁은 피크의 상단 복원.
      'topmost'                 - 기본. 임계값 이상 매칭인 가장 위(작은 y) 픽셀.
                                  상단 anti-alias 경계의 임계값 교차점을 선형 보간한다.
                                  좁은 피크 보존에 유리하지만 강도를 높게 잡을 수 있다.
      'argmin'                  - 가장 어두운(target에 가장 가까운) 픽셀.
                                  주의: 부드럽게 렌더링된 peak에서 선의 중심을 잡아 정점을 놓침.
      'centroid'                - 컬럼 전체 매칭 픽셀의 darkness-weighted centroid.
                                  굵은 곡선 / 노이즈 평균에 강함.

    Returns:
        list[Optional[float]] of length roi.shape[1].
        매칭 픽셀이 없는 컬럼은 None.
    """
    if roi.ndim != 3 or roi.shape[2] < 3:
        raise ValueError(f'roi must be HxWx3, got shape {roi.shape}')
    if method not in {'topmost', 'argmin', 'centroid', 'centerline'}:
        raise ValueError(f'Unknown extraction method: {method}')
    h, w = roi.shape[:2]
    if h == 0 or w == 0:
        return [None] * w
    target = np.asarray(curve_rgb, dtype=np.float32)

    # Accumulate per channel: avoid two H x W x 3 float temporaries.
    dist = np.zeros((h, w), dtype=np.float32)
    for channel in range(3):
        delta = np.subtract(roi[:, :, channel], target[channel], dtype=np.float32)
        dist += delta * delta
    np.sqrt(dist, out=dist)
    mask = dist < float(max_dist)  # H x W
    if float(np.ptp(target)) > 30.0:
        # Anti-aliased colors lie on the foreground/background line in RGB
        # space. A distance ball alone also admits gray grid and axis ink.
        background = np.asarray(sample_background_rgb(roi), dtype=np.float32)
        direction = target - background
        norm_sq = float(np.dot(direction, direction))
        if norm_sq > 1.0:
            projection = np.zeros((h, w), dtype=np.float32)
            energy = np.zeros((h, w), dtype=np.float32)
            for channel in range(3):
                delta = np.subtract(roi[:, :, channel], background[channel], dtype=np.float32)
                projection += delta * direction[channel]
                energy += delta * delta
            residual_sq = np.maximum(0.0, energy - projection * projection / norm_sq)
            # Scale tolerance by each pixel's contrast, not full stroke
            # contrast; otherwise pale gray grid lines slip through.
            mask &= residual_sq <= 10.0**2 + 0.15**2 * energy
    # Frame/border 감지: 가로 (row) 및 세로 (col) 양쪽으로 적용.
    # plot_box 테두리, 격자선, y/x 축 line 등이 curve 색상과 비슷할 때 topmost가 그걸 잡는 걸 방지.
    # 임계값 0.95: 진짜 frame은 거의 전체 폭/높이에 걸쳐 있으므로 0.95에서도 안정적으로 감지.
    # 0.70은 wide diffuse peak이 있는 noisy 패턴의 실제 데이터 row 까지 nuke 해서 over-aggressive.
    need_copy = True
    row_match_ratio = mask.sum(axis=1).astype(np.float32) / max(1, w)
    frame_rows = row_match_ratio > 0.95
    if frame_rows.any():
        if need_copy:
            mask = mask.copy()
            need_copy = False
        mask[frame_rows, :] = False

    # 세로 frame (y축 line, 우측 frame): col 의 매칭 픽셀 비율이 0.95 초과면 axis line 으로 간주.
    # 이 column 은 trace 후보에서 제외 (None 반환).
    # 추가로 frame col 인접 ±1 (dilate) 도 함께 제외 — axis line 의 AA spread / label tick 이
    # 인접 컬럼에 흘러들면 매칭 비율 0.8~0.9 정도로 0.95 임계값을 넘지 못하지만 trace 가 frame
    # 위쪽 끝(y≈0)을 잡아서 spike 가 생긴다.
    # 세로 임계값은 0.80 (가로 0.95 보다 낮음): 진짜 XRD 곡선은 한 column 에서 chart 높이의
    # 80% 이상 차지 못한다 (sharp peak 도 1-3 px 폭). 0.80 이상은 axis line / AA spread.
    col_match_ratio = mask.sum(axis=0).astype(np.float32) / max(1, h)
    frame_cols = col_match_ratio > 0.80
    if frame_cols.any():
        # dilate by 1
        fc_dilated = frame_cols.copy()
        fc_dilated[1:]  |= frame_cols[:-1]
        fc_dilated[:-1] |= frame_cols[1:]
        if need_copy:
            mask = mask.copy()
            need_copy = False
        mask[:, fc_dilated] = False

    has_match = mask.any(axis=0)

    if method == 'argmin':
        argmin_y = np.argmin(np.where(mask, dist, np.inf), axis=0)
        return [float(argmin_y[c]) if has_match[c] else None for c in range(w)]

    if method in {'centroid', 'centerline'}:
        weight = np.where(mask, np.maximum(1.0, float(max_dist) - dist), 0.0)
        w_sum = weight.sum(axis=0)
        ys_full = np.arange(h, dtype=np.float32)
        y_weighted = (weight * ys_full[:, None]).sum(axis=0)
        center = np.zeros(w, dtype=np.float64)
        np.divide(y_weighted, w_sum, out=center, where=w_sum > 0)
        if method == 'centroid':
            return [float(y) if valid else None for y, valid in zip(center, has_match)]

    # 기본: topmost + sub-pixel AA edge 보간.
    # 클러스터 centroid는 darkness-weighted라 커브 body 쪽으로 끌려 apex를 1-2px 놓치는 문제가 있다.
    # 대신 AA 전환점(dist가 max_dist를 가로지르는 sub-pixel 위치)을 선형 보간으로 찾는다.
    #
    # 원리:
    #   y = top_y - 1: 마스크 밖 픽셀 (dist > max_dist, 배경)
    #   y = top_y    : 마스크 안 첫 픽셀 (dist < max_dist, AA edge)
    #   두 점 사이 dist 가 max_dist 와 교차하는 sub-pixel y → 진짜 curve 상단
    columns = np.arange(w)
    top_y = np.argmax(mask, axis=0)
    d_at = dist[top_y, columns].astype(np.float64)
    d_above = dist[np.maximum(top_y - 1, 0), columns].astype(np.float64)
    denominator = d_above - d_at
    interpolate = (top_y > 0) & (d_above > max_dist) & (max_dist > d_at) & (denominator > 1e-6)
    fraction = np.zeros(w, dtype=np.float64)
    np.divide(d_above - max_dist, denominator, out=fraction, where=interpolate)
    ys = np.where(interpolate, top_y - 1 + fraction, top_y)
    if method == 'centerline':
        # Column centroids avoid the positive intensity bias of an upper
        # envelope, but average down unresolved narrow peaks. Restore only
        # prominent, narrow apex columns supported by the image itself.
        from scipy.signal import find_peaks

        if np.count_nonzero(has_match) >= 3:
            envelope = np.interp(columns, columns[has_match], ys[has_match])
            apex, _ = find_peaks(-envelope, prominence=0.08 * h, width=(None, 6.0))
            apex = apex[has_match[apex]]
            center[apex] = ys[apex]
        ys = center
    return [float(y) if valid else None for y, valid in zip(ys, has_match)]


def sample_background_rgb(roi: np.ndarray, patch: int = 20) -> Tuple[int, int, int]:
    """ROI 4 모서리 패치의 중앙값으로 배경 RGB 추정."""
    h, w = roi.shape[:2]
    p = max(1, min(int(patch), h // 8, w // 8))
    corners = np.concatenate([
        roi[:p, :p, :3].reshape(-1, 3),
        roi[:p, w - p:, :3].reshape(-1, 3),
        roi[h - p:, :p, :3].reshape(-1, 3),
        roi[h - p:, w - p:, :3].reshape(-1, 3),
    ], axis=0).astype(np.float32)
    med = np.median(corners, axis=0)
    return (int(round(med[0])), int(round(med[1])), int(round(med[2])))


def adaptive_max_dist(curve_rgb: Tuple[int, int, int], bg_rgb: Tuple[int, int, int],
                      fraction: float = 0.6, floor: float = 80.0) -> float:
    """bg ↔ curve 거리의 fraction을 매칭 임계값으로 사용 (anti-alias 흡수).
    fraction=0.6은 sub-pixel AA(거리 절반 지점)도 포함."""
    diff = np.asarray(curve_rgb, dtype=np.float32) - np.asarray(bg_rgb, dtype=np.float32)
    d = float(np.linalg.norm(diff))
    # The background must stay outside the matching ball even on faint curves.
    return min(max(float(floor), d * float(fraction)), 0.9 * d)


def sample_curve_rgb(
    roi: np.ndarray,
    color_sample_point: Tuple[int, int],
    plot_box: Tuple[int, int, int, int],
    patch_radius: int = 2,
    dark_search_radius: int = 30,
) -> Tuple[int, int, int]:
    """
    full-image 좌표 color_sample_point에서 ROI 픽셀 RGB를 샘플링.
    배경 대비가 가장 큰 실제 픽셀을 선택한다. 클릭이 배경이면 검색 반경을 넓힌다.
    """
    x0_pb, y0_pb = int(plot_box[0]), int(plot_box[1])
    h, w = roi.shape[:2]
    cx = max(0, min(w - 1, int(color_sample_point[0]) - x0_pb))
    cy = max(0, min(h - 1, int(color_sample_point[1]) - y0_pb))

    # A patch mean mixes thin foreground strokes with their background and
    # can exclude the actual stroke from the subsequent color-distance mask.
    # Sample an observed high-contrast pixel instead, for light or dark charts.
    background = np.asarray(sample_background_rgb(roi), dtype=np.float32)

    def strongest_pixel(radius: int):
        patch = roi[max(0, cy-radius):min(h, cy+radius+1),
                    max(0, cx-radius):min(w, cx+radius+1), :3].reshape(-1, 3)
        contrast = np.linalg.norm(patch.astype(np.float32) - background, axis=1)
        index = int(np.argmax(contrast))
        return patch[index], float(contrast[index])

    pixel, contrast = strongest_pixel(max(0, int(patch_radius)))
    if contrast < 20.0:
        pixel, _ = strongest_pixel(max(int(patch_radius), int(dark_search_radius)))
    return tuple(int(value) for value in pixel)
