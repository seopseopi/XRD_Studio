"""Render paired XRD images with one shared transform for curves and calibration.

Uses local numeric JSON files; writes only to the selected output directory.
Three simulated styles are generated per source pattern. These are not scans of
real publications. Source IDs listed in --development-manifest are development
data; all other IDs are held out at the pattern level (including all styles).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def render(x, y, domain, seed):
    rng = np.random.default_rng(seed)
    scale = 3
    width, height = 1200, 900
    box = [170, 90, 1120, 780]
    xmin, xmax = float(x[0]), float(x[-1])
    ymin, ymax = float(y.min()), float(y.max())
    span = ymax - ymin
    # Both ends have headroom, and the SAME limits are exported in mi.json.
    low, high = ymin - 0.04 * span, ymax + 0.08 * span
    px = box[0] + (x - xmin) / (xmax - xmin) * (box[2] - box[0])
    py = box[3] - (y - low) / (high - low) * (box[3] - box[1])
    bg = (255, 255, 255) if domain == 'clean' else (248, 249, 252)
    color = {'clean': (25, 25, 25), 'styled': (35, 95, 180), 'real_like': (115, 115, 115)}[domain]
    image = Image.new('RGB', (width * scale, height * scale), bg)
    draw = ImageDraw.Draw(image)
    if domain != 'clean':
        for gx in np.linspace(box[0], box[2], 8):
            draw.line([(gx*scale, box[1]*scale), (gx*scale, box[3]*scale)], fill=(225, 227, 232), width=2)
        for gy in np.linspace(box[1], box[3], 6):
            draw.line([(box[0]*scale, gy*scale), (box[2]*scale, gy*scale)], fill=(225, 227, 232), width=2)
    draw.rectangle(tuple(v*scale for v in box), outline=(35, 35, 35), width=4)
    draw.line(list(zip(px*scale, py*scale)), fill=color, width=5, joint='curve')
    image = image.resize((width, height), Image.Resampling.LANCZOS)
    if domain == 'real_like':
        image = image.filter(ImageFilter.GaussianBlur(0.35))
        arr = np.asarray(image).astype(float)
        arr += rng.normal(0, 2, arr.shape[:2])[:, :, None]
        image = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(image)
    for value, row in [(high, box[1]), (low, box[3])]:
        draw.text((20, row-5), f'{value:.6g}', fill=(35, 35, 35))
    for value, col in [(xmin, box[0]), (xmax, box[2])]:
        draw.text((col-10, box[3]+12), f'{value:.6g}', fill=(35, 35, 35))
    # A calibration click is supplied, just as by a user; no curve is passed to inference.
    index = len(x) // 2
    mi = {'plot_box': box, 'x_axis_points': [[box[0], box[3]], [box[2], box[3]]],
          'x_axis_values': [xmin, xmax], 'y_axis_points': [[box[0], box[3]], [box[0], box[1]]],
          'y_axis_values': [low, high], 'color_sample_point': [round(px[index]), round(py[index])],
          'legend_ignore_boxes': [], 'perspective_corners': None, 'color_resample_points': []}
    return image, mi


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-dir', type=Path, required=True)
    p.add_argument('--source-manifest', type=Path, required=True, help='CSV containing the selected sample_id values')
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--development-manifest', type=Path, default=Path('data/test_canonical_30/manifest.csv'))
    p.add_argument('--seed', type=int, default=20260909)
    args = p.parse_args()
    dev_ids = {r['sample_id'] for r in csv.DictReader(args.development_manifest.open())}
    manifests = {'development': [], 'holdout': []}
    source_ids = sorted({r['sample_id'] for r in csv.DictReader(args.source_manifest.open())})
    for sample_id in source_ids:
        source = args.source_dir / f'{sample_id}.json'
        data = json.loads(source.read_text())
        x = np.asarray(data.get('two_theta_values', []), dtype=float)
        y = np.asarray(data.get('intensities', []), dtype=float)
        if len(x) < 3 or x.shape != y.shape or not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)) or np.any(np.diff(x) <= 0) or np.ptp(y) <= 0:
            raise ValueError(f'Invalid numeric source: {source.name}')
        split = 'development' if source.stem in dev_ids else 'holdout'
        for domain in ['clean', 'styled', 'real_like']:
            test_id = f'{domain}_{source.stem}'
            seed = args.seed + int(hashlib.sha256(test_id.encode()).hexdigest()[:8], 16)
            image, mi = render(x, y, domain, seed)
            directory = args.output_dir / split / domain / source.stem
            directory.mkdir(parents=True, exist_ok=True)
            image.save(directory / 'input.png')
            (directory / 'mi.json').write_text(json.dumps(mi, indent=2)+'\n')
            (directory / 'gt.json').write_text(json.dumps({'x_values': x.tolist(), 'y_values': y.tolist()})+'\n')
            row = {'test_id': test_id, 'sample_id': source.stem, 'domain': domain, 'split': split,
                   'sha256_source': hashlib.sha256(source.read_bytes()).hexdigest(), 'render_seed': seed}
            for key, filename in [('input_image','input.png'), ('mi_json','mi.json'), ('gt_json','gt.json')]:
                path = directory / filename
                row[key] = path.relative_to(args.output_dir).as_posix()
                row['sha256_'+key] = hashlib.sha256(path.read_bytes()).hexdigest()
            manifests[split].append(row)
    for split, rows in manifests.items():
        if not rows:
            continue
        with (args.output_dir / f'{split}.csv').open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
        print(f'{split}: {len(rows)} images / {len(rows)//3} unique patterns')


if __name__ == '__main__':
    main()
