# 성능 개선과 재현 기록

2026-09-09 · 기준 버전 [`2736a85`](https://github.com/seopseopi/xrd_digitizer/commit/2736a85) 대비 기본 `runner.run_simple` 엔진을 비교했습니다. 웹 서버에 포함된 Python 사본에도 같은 수정을 적용했습니다.

## 결과

![스타일별 평균 MAE](assets/performance_comparison.png)

| 지표 | 이전 | 개선 후 | 조건 |
|---|---:|---:|---|
| 평균 정규화 MAE | 0.082135 | **0.013611** | 237개, 전체 GT x-grid |
| MAE 개선 사례 | — | **237 / 237** | 동일 이미지·축·GT 해시 확인 |
| 피크 재현율 | 60.64% | **62.57%** | 5% prominence, ±0.2° 일대일 매칭 |
| 피크 정밀도 | 89.11% | **99.94%** | 예측 피크가 없는 이전 2개는 정밀도 평균에서 제외 |
| 추론 시간 | 23.90 ms | **11.88 ms** | 이미지 로딩·import·HTTP 제외, 각 3회 중앙값의 평균 |
| 새 CLI 프로세스 실행 | 1.461 s | **0.748 s** | 샘플 1개, 이전/이후 교대 실행 각 7회 중앙값 |
| 950 → 20,000점 리샘플링 | 109.18 ms | **14.62 ms** | 연산만 각 10회 중앙값, 같은 출력 확인 |

**MAE 83.4% 감소**, CLI 실행 약 **1.95배**, 리샘플링 약 **7.47배** 가속입니다. 이 배수들은 서로 다른 측정 범위이며 전체 웹 요청 속도에 일괄 적용되지 않습니다. 하드웨어·프로세스 캐시·OS 부하에 따라 시간은 달라집니다.

[원시 측정 및 환경](benchmarks/2026-09-09/summary.json) · [전체 사례 CSV](benchmarks/2026-09-09/per_case.csv) · [분할 중복 검사](benchmarks/2026-09-09/split_audit.json)

## 무엇을 바꿨나

| 문제 | 적용한 변경 | 확인 방법 |
|---|---|---|
| 얇은 곡선을 주변 배경과 평균 내어 실제 곡선색을 놓침 | 클릭 주변에서 배경 대비가 큰 **실제 픽셀** 선택 | 밝은·어두운 배경 및 저대비 회귀 테스트 |
| 고정 최소 색상 임계값이 희미한 곡선의 배경까지 포함 | 임계값을 배경–곡선 거리의 90% 이하로 제한 | 회색 배경을 곡선으로 추적하던 실패 재현 |
| 색 곡선과 무채색 격자선이 RGB 거리만으로 혼동됨 | 배경과 곡선 사이 RGB 방향에서 벗어나는 픽셀 제외 | 색 곡선 + 회색 격자선 테스트 |
| 컬럼별 Python 반복과 큰 RGB 임시 배열 | 채널별 거리 누적, 전체 컬럼의 AA 경계 보간 벡터화 | 출력·경계·빈 컬럼 테스트 |
| `argmin` 방식이 마스크로 제거한 축을 다시 선택 | 제거된 픽셀의 비용을 무한대로 처리 | 검은 축과 회색 곡선 회귀 테스트 |
| 2점 보정에 매 프로세스 scikit-learn 로드 | 같은 2점 직선의 기울기·절편 직접 계산 | 두 축, 역방향, 큰 값, 퇴화 입력 테스트 |
| 리샘플링 시 출력점마다 원본 전체 탐색 | 정렬된 구간 검색 + 일괄 최댓값 연산 | 불균일 격자·20,000점에서 기존 정의와 비교 |

기본값은 피크 정점 보존을 위한 `topmost`입니다. `--trace-method centerline`도 실험했지만, 별도 검증에서 MAE 개선과 동시에 피크 재현율 저하가 나타나 **기본값으로 채택하지 않았습니다**. 이 옵션은 가중 중심선에 좁은 정점 복원을 더하며, 더 매끈한 곡선이 필요한 경우에 한해 비교해서 사용하세요.

## 데이터와 평가 범위

- 사용자가 지정한 `1. XRD` 하위의 로컬 `data/source_json` 수치 사본에서 기존 manifest의 **100개 패턴**을 사용했습니다. 원본 `row_data/opxrd`의 일부 파일은 클라우드 읽기 시간 초과가 있어 이번 실행은 읽을 수 있는 수치 사본을 기준으로 했습니다.
- 기존 canonical-30에 있던 **21개 고유 패턴**으로 개발하고, 나머지 **79개**로 회귀와 출시 설정을 검증했습니다. 패턴별 3가지 스타일이 같은 분할에 속하며 분할 간 동일 x/y 배열은 없습니다.
- 이 79개는 **출시 검증 세트**입니다. 결과를 보고 중심선 기본 적용을 기각하고 색상 필터를 점검했으므로 완전히 봉인된 최종 시험 세트라고 주장하지 않습니다. 기관·측정 계열 단위 분할도 아닙니다.
- 각 원본을 1200×900 이미지로 렌더링합니다. clean은 검은 곡선, styled는 파란 곡선과 격자, real_like는 회색 곡선·격자·블러·잡음입니다. **`real_like`도 생성 이미지이며 실제 논문 스캔이 아닙니다.** 다중 곡선·범례 겹침·회전은 이번 평가에 없습니다.
- 렌더링 seed는 고정되어 있습니다. 이미지·GT·보정 JSON의 SHA-256을 기록하며, 추론에는 이미지와 수동 보정값만 전달합니다. GT로 후보를 고르는 oracle 기능은 사용하지 않습니다.
- 사용자 원본 데이터와 대량 생성 이미지는 GitHub에 추가하지 않았습니다. 공개된 것은 평가 코드·선택 ID·해시·집계·사례별 지표입니다. 재현에는 해당 로컬 수치 데이터가 필요합니다.

### 기존 canonical 평가의 축 오류

로컬에 보존된 legacy `render_clean_dataset.py`는 곡선을 `y_max + 0.08 × range`까지의 축에 그리면서, 눈금과 `axis_metadata.y_max`에는 원래 `y_max`를 쓰는 코드가 있었습니다. 일부 canonical 이미지의 수치 비교에는 이 불일치가 섞여 있습니다.

이를 엔진에 8% 상수 보정으로 넣지 않았습니다. 새 렌더러는 곡선·눈금·수동 보정값에 **동일한 좌표 변환**을 사용합니다. 따라서 본 표는 과거 canonical-30 수치나 README의 ‘9만 개·0.0079·99.7%’와 직접 비교할 수 없습니다. 9만여 원본 파일의 존재는 전체 평가 완료의 증거가 아닙니다.

### 지표 정의와 남은 한계

`MAE = mean(abs(interp(prediction, GT.x) − GT.y)) / ptp(GT.y)`. 예측 범위 바깥의 GT 지점은 NumPy의 끝점 보간을 사용합니다. 피크는 GT와 예측에 같은 5% GT-range prominence를 적용하고 거리순으로 ±0.2° 내 일대일 매칭합니다. 평균은 패턴별 macro 평균입니다. 잡음에서 생긴 피크도 포함합니다.

평균 intensity range 비율은 **0.911 → 0.844**로 낮아졌습니다. 축·격자 오검출을 줄이는 것과 별개로 좁은 피크의 높이 손실은 남아 있습니다. clean 피크 재현율도 **63.77% → 62.61%**로 소폭 낮아집니다. 평균 오차 감소를 모든 종류의 정확도 향상으로 해석하면 안 됩니다.

## 재현

저장소 루트에서 실행합니다. 원본 사본 경로가 다르면 `--source-dir`만 바꾸세요.

```bash
python -m eval.render_benchmark \
  --source-dir data/source_json \
  --source-manifest docs/benchmarks/2026-09-09/sources.csv \
  --development-manifest docs/benchmarks/2026-09-09/development_ids.csv \
  --output-dir outputs/performance/calibrated100

python -m eval.benchmark \
  --manifest outputs/performance/calibrated100/holdout.csv \
  --data-root outputs/performance/calibrated100 \
  --output outputs/performance/holdout_after.json \
  --repeat 3 --label improved-topmost
```

기준 버전은 별도 checkout에서 동일 평가기를 실행합니다. 현재 작업물을 변경하지 않습니다.

```bash
git worktree add --detach ../xrd-baseline 2736a85
# 이전 엔진 실행에만 필요한 의존성
python -m pip install scikit-learn
cp eval/benchmark.py ../xrd-baseline/eval/benchmark.py
XRD_BENCH_ROOT="$PWD"
XRD_BENCH_PYTHON="$PWD/.venv/bin/python"
cd ../xrd-baseline
"$XRD_BENCH_PYTHON" -m eval.benchmark \
  --manifest "$XRD_BENCH_ROOT/outputs/performance/calibrated100/holdout.csv" \
  --data-root "$XRD_BENCH_ROOT/outputs/performance/calibrated100" \
  --output "$XRD_BENCH_ROOT/outputs/performance/holdout_before.json" \
  --repeat 3 --label 2736a85-before
```

저장소 루트로 돌아와 시간 측정과 그림도 다시 생성할 수 있습니다.

```bash
cd "$XRD_BENCH_ROOT"
python -m eval.benchmark_runtime --baseline-dir ../xrd-baseline
python -m pip install matplotlib
python -m eval.render_performance_report
```

공개 `summary.json`의 `resample_seconds`, `cold_cli_seconds`에 이번 원시 시간 측정값이 있습니다. 결과 표의 이미지 해시는 Pillow 버전에 따라 달라질 수 있습니다.

## 다음 개선 우선순위

1. **좁은 피크 높이** — 원본 해상도 한계를 명시하고 sub-column 모델을 검증합니다. MAE뿐 아니라 peak height·FWHM을 출시 조건으로 사용해야 합니다.
2. **실제 논문 평가** — 범례·복수 곡선·JPEG·축 기울기가 포함된 이미지를 별도 주석하고 기관/논문 단위로 분할합니다.
3. **사용자 응답 시간** — Python 프로세스를 유지하는 worker 방식으로 약 0.75초의 새 프로세스 비용을 줄일 수 있습니다. 동시 요청·메모리·오류 격리 검증이 선행되어야 합니다.
