"""Build public aggregate/per-case metrics and README figures from paired runs."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runs', type=Path, default=Path('outputs/performance'))
    p.add_argument('--output', type=Path, default=Path('docs/benchmarks/2026-09-09'))
    p.add_argument('--assets', type=Path, default=Path('docs/assets'))
    args = p.parse_args()
    before = json.loads((args.runs/'holdout_before.json').read_text())
    after = json.loads((args.runs/'holdout_after.json').read_text())
    old = {c['test_id']: c for c in before['cases']}
    new = {c['test_id']: c for c in after['cases']}
    if old.keys() != new.keys():
        raise ValueError('Paired runs must contain identical test IDs')
    rows = []
    for key, a in new.items():
        b = old[key]
        if a['sha256'] != b['sha256']:
            raise ValueError(f'Input mismatch: {key}')
        row = {'test_id': key, 'sample_id': a['sample_id'], 'domain': a['domain']}
        for metric in ['mae_norm', 'range_ratio', 'peak_precision', 'peak_recall', 'seconds_median']:
            row[f'{metric}_before'] = b[metric]
            row[f'{metric}_after'] = a[metric]
        row.update({'sha256_'+k:v for k,v in a['sha256'].items()})
        rows.append(row)
    args.output.mkdir(parents=True, exist_ok=True)
    args.assets.mkdir(parents=True, exist_ok=True)
    with (args.output/'per_case.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    micro = json.loads((args.runs/'resample.json').read_text())
    cold = json.loads((args.runs/'cold_comparison.json').read_text())
    code_paths = ['preprocess/simple_trace.py', 'runner/run_simple.py', 'calibrate/axis_mapping.py',
                  'calibrate/numeric_export.py', 'eval/benchmark.py', 'eval/render_benchmark.py']
    summary = {'baseline_revision': before['revision'], 'environment': after['environment'],
               'protocol': after['protocol'], 'before': before['summary'], 'after': after['summary'],
               'mae_improved_cases': sum(a['mae_norm_after'] < a['mae_norm_before'] for a in rows),
               'mae_regressed_cases': sum(a['mae_norm_after'] > a['mae_norm_before'] for a in rows),
               'resample_seconds': micro, 'cold_cli_seconds': cold,
               'code_sha256': {name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in code_paths}}
    (args.output/'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')

    plt.rcParams.update({'font.family':'DejaVu Sans', 'font.size':11, 'axes.spines.top':False,
                         'axes.spines.right':False, 'axes.spines.left':False, 'axes.spines.bottom':False})
    navy, teal, muted = '#12243a', '#008b83', '#a6b4c4'
    fig, axes = plt.subplots(1, 3, figsize=(13.6, 4.5), layout='constrained')
    fig.suptitle('Measured on 237 generated images · 79 source patterns', fontsize=18, fontweight='bold', color=navy)
    for ax, domain, label in zip(axes, ['clean','styled','real_like'], ['Clean','Color + grid','Low contrast + noise']):
        vals = [before['summary'][domain]['mae_norm_mean'], after['summary'][domain]['mae_norm_mean']]
        bars=ax.bar(['Before','After'], vals, color=[muted,teal], width=.5)
        ax.set_title(label, fontweight='bold', color=navy, pad=12)
        ax.set_ylim(0,max(vals)*1.3)
        ax.set_ylabel('Normalized MAE ↓')
        ax.bar_label(bars, labels=[f'{v:.4f}' for v in vals], padding=6, fontweight='bold')
        ax.grid(axis='y', alpha=.12);ax.set_axisbelow(True)
        ax.text(.5,-.16,'79 images · per-panel scale',transform=ax.transAxes,ha='center',fontsize=9,color='#657589')
    fig.savefig(args.assets/'performance_comparison.png',dpi=160,bbox_inches='tight');plt.close(fig)

    # Explicitly show the worst baseline failure as a diagnostic example.
    example = max(old, key=lambda k:old[k]['mae_norm'])
    a, b = new[example], old[example]
    data = args.runs/'calibrated100'
    manifest = {r['test_id']:r for r in csv.DictReader((data/'holdout.csv').open())}
    gt=json.loads((data/manifest[example]['gt_json']).read_text())
    gx,gy=np.asarray(gt['x_values']),np.asarray(gt['y_values']); span=np.ptp(gy);lo=gy.min()
    fig, axes=plt.subplots(1,2,figsize=(13.6,4.2),layout='constrained')
    from PIL import Image
    axes[0].imshow(Image.open(data/manifest[example]['input_image']));axes[0].axis('off')
    axes[0].set_title('Input · generated low-contrast chart',loc='left',fontweight='bold',color=navy)
    ax=axes[1]
    ax.plot(gx,(gy-lo)/span,color=navy,lw=1.4,label='Source data',alpha=.7)
    for item,label,color in [(b,'Before','#d88967'),(a,'After',teal)]:
        pred=item['prediction'];ax.plot(pred['two_theta_values'],(np.asarray(pred['intensities'])-lo)/span,color=color,lw=1.1,label=label)
    ax.set_xlabel('2θ (degrees)');ax.set_ylabel('Normalized intensity');ax.legend(frameon=False,loc='center right',bbox_to_anchor=(1,.72))
    ax.set_title('Reconstruction · same calibration',loc='left',fontweight='bold',color=navy);ax.grid(alpha=.12)
    fig.suptitle(f'Diagnostic example: {example} (largest baseline MAE)',fontsize=13,color=navy)
    fig.savefig(args.assets/'extraction_comparison.png',dpi=160,bbox_inches='tight');plt.close(fig)

    # A restrained, data-derived header rather than stock artwork.
    source=json.loads(Path('data/test_canonical_30/clean/pattern_11832/gt.json').read_text())
    x=np.asarray(source['x_values']);y=np.asarray(source['y_values']);y=(y-y.min())/np.ptp(y)
    fig=plt.figure(figsize=(14,4.5),facecolor=navy)
    fig.text(.055,.81,'XRD  /  DIGITIZER',color='#6de0cc',fontsize=13,fontweight='bold')
    fig.text(.055,.53,'From chart\nto data.',color='white',fontsize=37,fontweight='bold',linespacing=1.2)
    fig.text(.057,.18,'Extract curves. Recover peaks. Export numbers.',color='#bbcada',fontsize=12)
    ax=fig.add_axes([.50,.20,.45,.62],facecolor=navy)
    ax.plot(x,y,color='#6de0cc',lw=1.6);ax.fill_between(x,0,y,color='#6de0cc',alpha=.10)
    ax.set_xticks([]);ax.set_yticks([]);ax.set_ylim(-.05,1.15)
    ax.text(.01,-.13,'pattern_11832  ·  source XRD signal',transform=ax.transAxes,color='#9bafc5',fontsize=10)
    fig.savefig(args.assets/'hero.png',dpi=150,facecolor=navy);plt.close(fig)
    print(json.dumps({k:summary[k] for k in ['mae_improved_cases','mae_regressed_cases']},indent=2))


if __name__ == '__main__':
    main()
