"""Printed peak-number OCR evaluation with known labels and text locations."""
import json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont,ImageFilter
from preprocess.auto_detect import _read_plot_annotations


def render(seed=0, scale=1., dark=False, blur=False):
    w,h=int(1200*scale),int(780*scale); box=[int(v*scale) for v in [140,80,1140,650]]
    left,top,right,bottom=box; bg='#1b232b' if dark else 'white';ink='#edf1f4' if dark else '#202932'
    image=Image.new('RGB',(w,h),bg);d=ImageDraw.Draw(image)
    fonts=['/System/Library/Fonts/Supplemental/Arial.ttf','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
    font=next((ImageFont.truetype(p,int(20*scale)) for p in fonts if Path(p).exists()),ImageFont.load_default())
    values=[18.25,29.64,43.18,57.32,72.06]
    centres=np.array([left+(v-10)/70*(right-left) for v in values]);amps=np.array([.52,.70,.45,.63,.77])
    x=np.arange(left,right+1); y=np.ones_like(x,dtype=float)*.07
    for center,amp in zip(centres,amps):y+=amp*np.exp(-.5*((x-center)/(5*scale))**2)
    d.line(list(zip(x,bottom-y*(bottom-top))),fill='#3ab39c' if dark else '#205f9f',width=max(1,int(2*scale)))
    d.rectangle(box,outline=ink,width=max(1,int(2*scale)))
    truth=[]
    for v,c,a in zip(values,centres,amps):
        yy=bottom-(a+.07)*(bottom-top)-int(17*scale)
        d.text((c,yy),str(v),font=font,fill=ink,anchor='mb')
        truth.append({'value':v,'label_center_x':float(c)})
    for i in range(6):
        xx=left+(right-left)*i/5;yy=bottom-(bottom-top)*i/5
        d.text((xx,bottom+12*scale),str(10+14*i),font=font,fill=ink,anchor='mt')
        d.text((left-12*scale,yy),str(i*2000),font=font,fill=ink,anchor='rm')
    if blur:image=image.filter(ImageFilter.GaussianBlur(.55))
    return image,box,truth


def main():
    out=Path('outputs/axis_detection/annotations');out.mkdir(parents=True,exist_ok=True);rows=[]
    for i,(scale,dark,blur) in enumerate([(1,False,False),(.8,False,False),(1.2,False,False),(1,True,False),(1,False,True),(.8,False,True)]):
        image,box,truth=render(i,scale,dark,blur);image.save(out/f'labels_{i}.png')
        found,status=_read_plot_annotations(np.asarray(image),*box)
        matched=set();correct=0
        for item in found:
            for j,gt in enumerate(truth):
                x,_,width,_=item['bbox']
                if j not in matched and abs(item['value']-gt['value'])<.005 and abs(x+width/2-gt['label_center_x'])<30*scale:
                    correct+=1;matched.add(j);break
        rows.append({'case':i,'scale':scale,'dark':dark,'blur':blur,'truth':truth,'found':found,'correct':correct,'expected':len(truth),'status':status})
    tp=sum(r['correct'] for r in rows);n=sum(len(r['found']) for r in rows);gt=sum(r['expected'] for r in rows)
    summary={'cases':len(rows),'correct':tp,'detected':n,'expected':gt,'precision':tp/n if n else 0,'recall':tp/gt}
    (out/'per_case.json').write_text(json.dumps(rows,indent=2));(out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary))

if __name__=='__main__':main()
