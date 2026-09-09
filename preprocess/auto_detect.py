"""Axis geometry, foreground colour and position-aware numeric tick detection.

Only straight, axis-aligned plots are supported. Scores measure line support,
not calibrated probabilities. Unreadable numeric scales remain unset.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from typing import Any

import numpy as np
from PIL import Image
from scipy import ndimage as ndi


def _to_gray(arr):
    return np.dot(arr[..., :3].astype(np.float32), [0.299, 0.587, 0.114])


def _ink(arr):
    gray = _to_gray(arr)
    # Modal intensity is robust to dark backgrounds and coloured plot panels.
    bg = np.argmax(np.bincount(gray.astype(np.uint8).ravel(), minlength=256))
    distance = np.abs(gray - bg)
    threshold = max(18, min(75, float(np.percentile(distance, 99.5)) * .4))
    return distance > threshold, distance


def _segments(mask, horizontal):
    axis = 1 if horizontal else 0
    length = mask.shape[axis]
    closed = ndi.maximum_filter1d(mask, 3, axis=axis, mode='constant')
    closed = ndi.minimum_filter1d(closed, 3, axis=axis, mode='constant')
    size = max(15, int(length * .22)) | 1
    opened = ndi.minimum_filter1d(closed, size, axis=axis, mode='constant')
    opened = ndi.maximum_filter1d(opened, size, axis=axis, mode='constant')
    labels, _ = ndi.label(opened)
    segments = []
    for sl in ndi.find_objects(labels):
        if sl is None:
            continue
        along, across = (sl[1], sl[0]) if horizontal else (sl[0], sl[1])
        if across.stop - across.start > max(12, mask.shape[1-axis] * .025):
            continue
        segments.append(((across.start + across.stop - 1) / 2,
                         along.start, along.stop - 1))
    return sorted(segments, key=lambda s: s[2]-s[1], reverse=True)[:32]


def _detect_axes(arr: np.ndarray) -> dict[str, Any]:
    h, w = arr.shape[:2]
    mask, _ = _ink(arr)
    hs, vs = _segments(mask, True), _segments(mask, False)
    candidates = []
    tolerance = max(6, min(h, w) * .018)
    for bottom, left_end, right in hs:
        for left, top, bottom_end in vs:
            gap = abs(left_end-left) + abs(bottom_end-bottom)
            width, height = right-left, bottom-top
            if gap > 2*tolerance or width < .25*w or height < .25*h:
                continue
            if left < 2 or top < 2 or right >= w-2 or bottom >= h-2:
                continue
            score = width*height/(w*h) * np.exp(-gap/(2*tolerance))
            candidates.append((score, left, top, right, bottom))
    empty = dict(x_axis_row=0, y_axis_col=0, right_col=0, top_row=0,
                 x_conf=0., y_conf=0., r_conf=0., t_conf=0., valid=False)
    if not candidates:
        return empty
    candidates.sort(reverse=True)
    best = candidates[0]
    # Two comparably sized disjoint panels need an explicit user selection.
    for other in candidates[1:]:
        if other[0] > best[0]*.9 and abs(other[1]-best[1]) > .2*w:
            return empty
    _, left, top, right, bottom = best
    # Snap to centres of the other frame lines where available.
    for pos, start, end in hs:
        if abs(pos-top) < tolerance and abs(start-left) < tolerance and abs(end-right) < tolerance:
            top = pos
            break
    for pos, start, end in vs:
        if abs(pos-right) < tolerance and abs(start-top) < tolerance and abs(end-bottom) < tolerance:
            right = pos
            break
    left, top, right, bottom = [int(round(v)) for v in (left, top, right, bottom)]
    def support(horizontal, pos, start, end):
        strip = mask[max(0,pos-2):pos+3, start:end+1] if horizontal else mask[start:end+1, max(0,pos-2):pos+3]
        return float(np.mean(np.any(strip, axis=0 if horizontal else 1)))
    return dict(x_axis_row=bottom, y_axis_col=left, right_col=right, top_row=top,
                x_conf=support(True,bottom,left,right), y_conf=support(False,left,top,bottom),
                r_conf=support(False,right,top,bottom), t_conf=support(True,top,left,right), valid=True)


def _detect_curve_color(arr, x_row, y_col, r_col, t_row):
    pad = max(5, int(min(r_col-y_col,x_row-t_row)*.015))
    roi = arr[t_row+pad:x_row-pad, y_col+pad:r_col-pad]
    if not roi.size:
        return None
    mask, distance = _ink(roi)
    # Suppress faint grids, retain actual black trace pixels.
    if not mask.any():
        return None
    mask &= distance >= np.percentile(distance[mask], 60)
    pixels = roi[mask]
    bins = pixels.astype(int)//24
    ids = bins[:,0]*121 + bins[:,1]*11 + bins[:,2]
    best = np.bincount(ids).argmax()
    yy, xx = np.where(mask)
    chosen = np.where(ids == best)[0]
    i = chosen[np.argmin((xx[chosen]-roi.shape[1]/2)**2 + (yy[chosen]-roi.shape[0]/2)**2)]
    return pixels[i].tolist(), [int(xx[i]+y_col+pad), int(yy[i]+t_row+pad)]


def _parse_number(text):
    text = text.strip().replace('−','-').replace('–','-')
    if re.fullmatch(r'[+-]?\d{1,3}(,\d{3})+(\.\d+)?',text):
        text = text.replace(',','')
    if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', text):
        return None
    value = float(text)
    return value if np.isfinite(value) else None


def _fit_ticks(ticks, start, end):
    """Consensus affine fit; at least three positioned, consistent tick values."""
    if len(ticks) < 3:
        return None, {'status':'insufficient_ticks','ticks':len(ticks)}
    p, v = np.array([(t[0],t[1]) for t in ticks]).T
    best = None
    for i in range(len(p)):
        for j in range(i):
            if abs(p[i]-p[j]) < abs(end-start)*.25 or v[i] == v[j]:
                continue
            slope = (v[i]-v[j])/(p[i]-p[j]); offset = v[i]-slope*p[i]
            residual = np.abs((v-offset)/slope-p)
            inliers = residual < max(3,abs(end-start)*.012)
            count = int(inliers.sum())
            if count < 3 or np.ptp(p[inliers]) < abs(end-start)*.45:
                continue
            score = (count, -float(residual[inliers].mean()))
            if best is None or score > best[0]:
                best = (score,inliers)
    if best is None or best[0][0] < max(3, len(ticks)*.6):
        return None, {'status':'inconsistent_ticks','ticks':len(ticks)}
    indices = best[1]
    slope, offset = np.polyfit(p[indices],v[indices],1)
    result = [float(slope*start+offset),float(slope*end+offset)]
    return result, {'status':'read','ticks':int(indices.sum()),'total_ticks':len(ticks)}


def _try_ocr(arr, bottom, left, right, top):
    values = dict(x_min=None,x_max=None,y_min=None,y_max=None)
    status = {k:{'status':'unavailable'} for k in ('x','y')}
    try:
        import pytesseract
        cmd = shutil.which('tesseract') or shutil.which('/opt/homebrew/bin/tesseract')
        if not cmd:
            return values,False,status
        pytesseract.pytesseract.tesseract_cmd = cmd
        h,w = arr.shape[:2]
        crops = {'x':(max(0,left-60),bottom+5,min(w,right+60),min(h,bottom+max(35,int(h*.09)))),
                 'y':(max(0,left-max(80,int(w*.12))),max(0,top-20),left-5,min(h,bottom+20))}
        for axis,(x0,y0,x1,y1) in crops.items():
            if x1<=x0 or y1<=y0:
                status[axis] = {'status':'no_label_margin'}
                continue
            region = Image.fromarray(arr[y0:y1,x0:x1])
            region = region.resize((region.width*3,region.height*3),Image.Resampling.LANCZOS)
            data = pytesseract.image_to_data(region,config='--psm 11',output_type=pytesseract.Output.DICT,timeout=12)
            tokens=[]
            for i,text in enumerate(data['text']):
                value=_parse_number(text)
                if value is None or float(data['conf'][i]) < 15:
                    continue
                x=x0+(data['left'][i]+data['width'][i]/2)/3
                y=y0+(data['top'][i]+data['height'][i]/2)/3
                tokens.append((x if axis=='x' else y,value,y if axis=='x' else x))
            if axis=='x' and tokens:
                closest=min(t[2] for t in tokens)
                tokens=[t for t in tokens if t[2]-closest < max(10,h*.02)]
            fitted, info = _fit_ticks(tokens, left if axis=='x' else bottom, right if axis=='x' else top)
            status[axis]=info
            if fitted:
                values[axis+'_min'],values[axis+'_max']=fitted
        return values,True,status
    except Exception as exc:
        # OCR is optional; missing executables/timeouts must not lose geometry.
        status['error']=type(exc).__name__
        return values,False,status


def _read_plot_annotations(arr, left, top, right, bottom):
    """Read printed numeric labels inside the plot; these are not axis values.

    Text-box positions locate the annotation, not the underlying peak. Retain
    OCR candidates for visual review; never infer physical units from a label.
    """
    try:
        import pytesseract
        cmd = shutil.which('tesseract') or shutil.which('/opt/homebrew/bin/tesseract')
        if not cmd:
            return [], 'unavailable'
        pytesseract.pytesseract.tesseract_cmd = cmd
        pad = 6
        roi = arr[top+pad:bottom-pad,left+pad:right-pad]
        if not roi.size:
            return [], 'empty'
        region = Image.fromarray(roi)
        scale = min(3, max(1, 2400 // max(region.size)))
        region = region.resize((region.width*scale, region.height*scale), Image.Resampling.LANCZOS)
        data = pytesseract.image_to_data(region, config='--psm 11', output_type=pytesseract.Output.DICT, timeout=15)
        labels = []
        for i, text in enumerate(data['text']):
            value = _parse_number(text)
            confidence = float(data['conf'][i])
            if value is None or confidence < 30:
                continue
            x = int(round(left+pad+data['left'][i]/scale))
            y = int(round(top+pad+data['top'][i]/scale))
            width = int(round(data['width'][i]/scale))
            height = int(round(data['height'][i]/scale))
            labels.append({'text':text.strip(), 'value':value, 'bbox':[x,y,width,height],
                           'ocr_score':round(confidence,1), 'reviewed':False})
        return sorted(labels, key=lambda item:item['bbox'][0]), 'read' if labels else 'no_numeric_labels'
    except Exception as exc:
        return [], 'error:' + type(exc).__name__


def auto_detect(image_path: str) -> dict[str, Any]:
    try:
        with Image.open(image_path) as img:
            arr = np.asarray(img.convert('RGB'))
    except Exception as exc:
        return {'success':False,'error':f'이미지 열기 실패: {exc}','ocr_available':False}
    axes = _detect_axes(arr)
    if not axes['valid']:
        return {'success':False,'error':'명확한 축 교점을 찾지 못했습니다. 그래프 하나만 잘라 넣거나 영역을 직접 지정하세요.','confidence':0,'ocr_available':False}
    left,top,right,bottom = [axes[k] for k in ('y_axis_col','top_row','right_col','x_axis_row')]
    color = _detect_curve_color(arr,bottom,left,right,top)
    values,available,status = _try_ocr(arr,bottom,left,right,top)
    annotations, annotation_status = _read_plot_annotations(arr,left,top,right,bottom)
    warnings=[]
    for axis in ('x','y'):
        if status[axis]['status'] != 'read':
            warnings.append(f'{axis.upper()}축 숫자를 확인하고 직접 입력하세요.')
    return {'success':True,'calib_points':{'p1':{'x':left,'y':bottom},'p2':{'x':right,'y':bottom},'p3':{'x':left,'y':top}},
            'curve_color':color[0] if color else None,'color_sample_point':color[1] if color else None,
            'axis_values':values,'ocr_available':available,'ocr_status':status,'warnings':warnings,
            'confidence':round((axes['x_conf']+axes['y_conf'])/2,3),'confidence_kind':'line_support','annotations':annotations,'annotation_status':annotation_status,'error':None}


if __name__ == '__main__':
    print(json.dumps(auto_detect(sys.argv[1]),ensure_ascii=False,indent=2))
