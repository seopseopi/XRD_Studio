"""Reproducible synthetic axis benchmark with an optional previous implementation.

python -m eval.benchmark_axes --baseline outputs/axis_detection/baseline_auto_detect.py
Images/ground truth stay in outputs; aggregate + per-case metrics may be published.
"""
import argparse
import importlib.util
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from preprocess import auto_detect as current


def render_case(seed, style):
    rng = np.random.default_rng(seed)
    w,h = int(rng.integers(700,1500)),int(rng.integers(500,1000))
    left,top = int(w*rng.uniform(.13,.22)),int(h*rng.uniform(.08,.18))
    right,bottom = int(w*rng.uniform(.80,.94)),int(h*rng.uniform(.75,.85))
    dark = style=='dark'
    bg,ink = ((27,35,43),(236,240,245)) if dark else ((255,255,255),(25,30,35))
    im=Image.new('RGB',(w,h),bg);d=ImageDraw.Draw(im)
    thickness=int(rng.integers(1,4))
    if style=='grid':
        for x in np.linspace(left,right,6): d.line((x,top,x,bottom),fill=(210,215,220))
        for y in np.linspace(top,bottom,6): d.line((left,y,right,y),fill=(210,215,220))
    x=np.linspace(left,right,right-left+1); y=np.zeros_like(x)+.06
    for _ in range(18):
        center=rng.uniform(left,right); width=rng.uniform(.7,9)
        y+=rng.uniform(.05,.8)*np.exp(-.5*((x-center)/width)**2)
    y=y/(y.max()*1.12)
    points=list(zip(x, bottom-y*(bottom-top)))
    d.line(points,fill=(58,179,156) if dark else (31,95,161),width=2)
    d.line((left,top,left,bottom,right,bottom),fill=ink,width=thickness)
    if style!='open':d.line((left,top,right,top,right,bottom),fill=ink,width=thickness)
    font_paths=['/System/Library/Fonts/Supplemental/Arial.ttf','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
    font=next((ImageFont.truetype(p,16) for p in font_paths if Path(p).exists()),ImageFont.load_default())
    for i in range(6):
        xx=left+(right-left)*i/5; yy=bottom-(bottom-top)*i/5
        d.line((xx,bottom,xx,bottom+5),fill=ink,width=1)
        d.text((xx,bottom+10),str(10+14*i),font=font,fill=ink,anchor='mt')
        d.line((left-5,yy,left,yy),fill=ink,width=1)
        d.text((left-10,yy),str(2000*i),font=font,fill=ink,anchor='rm')
    if style=='blur':im=im.filter(ImageFilter.GaussianBlur(.7))
    if style=='noise':
        a=np.array(im).astype(float)+rng.normal(0,4,(h,w,1))
        im=Image.fromarray(np.clip(a,0,255).astype('uint8'))
    return im,[left,top,right,bottom]


def evaluate(module, im, path, gt, ocr):
    start=time.perf_counter();a=module._detect_axes(np.asarray(im));dt=time.perf_counter()-start
    pred=[a['y_axis_col'],a['top_row'],a['right_col'],a['x_axis_row']]
    valid=a.get('valid',min(a['x_conf'],a['y_conf'])>=.15)
    err=np.abs(np.array(pred)-gt)
    result={'pred':pred,'valid':bool(valid),'boundary_mae_px':float(err.mean()),'within_3px':bool(valid and err.max()<=3),'geometry_ms':round(dt*1000,2)}
    if ocr:
        detection=module.auto_detect(str(path));v=detection.get('axis_values') or {}
        errors=[]
        for k,target,span in [('x_min',10,70),('x_max',80,70),('y_min',0,10000),('y_max',10000,10000)]:
            value=v.get(k)
            errors.append(abs(value-target)/span if value is not None else None)
        result['ocr_values']=v;result['ocr_max_relative_error']=max(errors) if all(x is not None for x in errors) else None
        result['ocr_within_1pct']=all(x is not None and x<=.01 for x in errors)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--baseline');p.add_argument('--output',default='outputs/axis_detection/stress');args=p.parse_args()
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    modules={'after':current}
    if args.baseline:
        spec=importlib.util.spec_from_file_location('axis_baseline',args.baseline);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old);modules['before']=old
    rows=[]
    for i in range(48):
        style=['clean','open','grid','dark','blur','noise'][i%6];seed=9102026+i
        im,gt=render_case(seed,style);path=out/f'{i:02d}_{style}.png';im.save(path)
        row={'case':path.name,'seed':seed,'style':style,'plot_box':gt,'size':list(im.size)}
        for name,module in modules.items():row[name]=evaluate(module,im,path,gt,i<12)
        rows.append(row)
    summary={}
    for name in modules:
        scores=[r[name] for r in rows];ocr=[s for s in scores if 'ocr_within_1pct' in s]
        summary[name]={'cases':len(scores),'within_3px':sum(s['within_3px'] for s in scores),'boundary_mae_px':float(np.mean([s['boundary_mae_px'] for s in scores])),'median_geometry_ms':float(np.median([s['geometry_ms'] for s in scores])),'ocr_cases':len(ocr),'ocr_within_1pct':sum(s['ocr_within_1pct'] for s in ocr)}
    (out/'per_case.json').write_text(json.dumps(rows,indent=2));(out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
