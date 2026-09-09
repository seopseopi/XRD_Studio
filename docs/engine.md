# 엔진 가이드

웹의 기본 엔진은 `runner.run_simple`입니다. ROI 안에서 곡선 색상을 찾고, 컬럼별 픽셀 경계를 추출한 뒤 축 보정으로 `(2θ, intensity)`를 복원합니다. 학습된 가중치 없이 실행됩니다.

## 엔진 선택

| 엔진 | 실행 모듈 | 용도 |
|---|---|---|
| 기본 픽셀 추출 | `runner.run_simple` | 단색 곡선, 빠른 수치 복원 |
| Classical DP | `runner.run_local` | 후보 생성·연속 경로·복구 단계 진단 |
| ML 실험 | `runner.run_ml_curve` | 별도 모델 가중치와 PyTorch가 있는 경우 |

```bash
# 기본값: 상단 anti-alias 경계 추출
python -m runner.run_simple \
  --image_path examples/sample.png \
  --manual_inputs_path examples/sample_mi.json \
  --output_json_path result.json

# 중심선 실험: MAE와 피크 높이·재현율을 함께 비교할 것
python -m runner.run_simple \
  --image_path examples/sample.png \
  --manual_inputs_path examples/sample_mi.json \
  --trace-method centerline --output_json_path centerline.json

# DP 엔진, 2배 ROI 확대
python -m runner.run_local \
  --image_path examples/sample.png \
  --manual_inputs_path examples/sample_mi.json \
  --roi-upscale-factor 2 --output_json_path classic.json --no-debug
```

`--trace-method`는 `topmost`(기본), `centroid`, `centerline`, `argmin`을 지원합니다. `--smooth`는 좁은 피크를 평탄하게 만들 수 있어 기본적으로 꺼져 있습니다. `--color-max-dist`는 자동 색상 임계값을 수동 값으로 바꿉니다.

## 보정값과 출력

[샘플 보정 JSON](../examples/sample_mi.json)에는 ROI, x/y 축의 두 좌표와 대응 수치, 곡선 색상 클릭 지점이 있습니다. 좌표는 원본 이미지 기준입니다. 축은 두 점을 지나는 직선으로 변환합니다.

출력에는 `two_theta_values`, `intensities`, `peaks_numeric_curve`, `warnings`, `model_assist`가 포함됩니다. `model_assist.trace_method`와 `stage_timings`로 실행 방식을 확인할 수 있습니다. 현재 `confidence`는 주로 축 보정의 일관성이므로 곡선 정확도의 보증으로 해석하지 마세요.

## 코드 구조

```text
core/          입력·출력 타입, 설정
preprocess/    ROI, 색상, 픽셀 추출
trace/         DP 후보·경로·후처리
calibrate/     축 보정, 수치 export, 피크
runner/        CLI 진입점
eval/          평가, 보정된 렌더링, 시각 보고서
tests/         회귀 테스트
web/client/    React 작업 공간
web/server/    Express API + Python subprocess
```

웹 기본 Python 코드는 `web/server/analysis/python/xrd_digitizer`에 포함됩니다. 테스트에서 핵심 파일의 루트/웹 사본 일치를 검사합니다. 웹은 `XRD_USE_CLASSIC=true` 또는 `XRD_USE_ML=true`로 엔진을 바꿀 수 있습니다. 자세한 환경변수는 [웹 가이드](../web/README.md)를 참고하세요.
