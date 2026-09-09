"""Geometry abstention, numeric scale safety and stable axis contracts."""
import numpy as np
import pytest
from PIL import Image, ImageDraw
from preprocess.auto_detect import _detect_axes, _fit_ticks, _parse_number, auto_detect
from eval.benchmark_axes import render_case


@pytest.mark.parametrize('style', ['clean','open','grid','dark','blur','noise'])
def test_axis_segments_handle_peaks_and_backgrounds(style):
    image, expected = render_case(13519, style)
    found = _detect_axes(np.asarray(image))
    assert found['valid']
    actual = [found[k] for k in ('y_axis_col','top_row','right_col','x_axis_row')]
    assert np.max(np.abs(np.array(actual)-expected)) <= 3


@pytest.mark.parametrize('kind', ['white','dark','noise','text','single_line','two_panels'])
def test_non_unique_or_missing_axes_abstain(kind):
    image = Image.new('RGB',(900,600),'white' if kind!='dark' else 'black')
    draw = ImageDraw.Draw(image)
    if kind=='noise':
        image = Image.fromarray(np.random.default_rng(191).integers(0,256,(600,900,3),dtype=np.uint8))
    elif kind=='text':draw.text((100,300),'No graph: 10 20 30 40',fill='black')
    elif kind=='single_line':draw.line((120,400,800,400),fill='black',width=2)
    elif kind=='two_panels':
        draw.rectangle((60,100,380,500),outline='black',width=2)
        draw.rectangle((510,100,830,500),outline='black',width=2)
    assert not _detect_axes(np.asarray(image))['valid']


def test_tick_fit_preserves_large_intensity_and_ignores_decimal_outlier():
    ticks=[(500,0,0),(400,20000,0),(300,40000,0),(200,60000,0),(100,8000000,0),(0,100000,0)]
    values, info = _fit_ticks(ticks,500,0)
    assert info['ticks']==5
    np.testing.assert_allclose(values,[0,100000],atol=1e-6)


def test_tick_fit_interpolates_interior_ticks_to_boundaries():
    values, _ = _fit_ticks([(100,20,0),(200,30,0),(300,40,0),(400,50,0)],0,500)
    np.testing.assert_allclose(values,[10,60])


def test_unreliable_ocr_does_not_invent_scale():
    assert _fit_ticks([(0,0,0),(100,10,0)],0,100)[0] is None
    assert _fit_ticks([(0,1,0),(100,10,0),(200,100,0),(300,1000,0)],0,300)[0] is None


@pytest.mark.parametrize('text', ['Intensity100','1.2.3','1,23','nan','inf','10^3'])
def test_numeric_parser_rejects_ambiguous_tokens(text):
    assert _parse_number(text) is None


def test_numeric_parser_supports_signed_decimal_and_exponent():
    assert _parse_number('−0.25') == -.25
    assert _parse_number('1,200') == 1200
    assert _parse_number('2e4') == 20000


def test_unreadable_image_returns_actionable_error(tmp_path):
    result = auto_detect(str(tmp_path/'missing.png'))
    assert not result['success'] and result['error']


def test_annotation_ocr_returns_printed_value_and_absolute_box(monkeypatch):
    import sys
    from types import SimpleNamespace
    from preprocess.auto_detect import _read_plot_annotations
    fake = SimpleNamespace(pytesseract=SimpleNamespace(), Output=SimpleNamespace(DICT='dict'),
        image_to_data=lambda *a, **k: {'text':['18.25','Intensity','9.8'], 'conf':[95,98,12],
            'left':[30,60,90], 'top':[24,48,72], 'width':[60,60,30], 'height':[30,30,30]})
    monkeypatch.setitem(sys.modules,'pytesseract',fake)
    monkeypatch.setattr('shutil.which',lambda _: '/test/tesseract')
    labels,status=_read_plot_annotations(np.full((400,600,3),255,dtype=np.uint8),100,50,500,350)
    assert status=='read' and len(labels)==1
    assert labels[0]['value']==18.25
    assert labels[0]['bbox']==[116,64,20,10]
    assert not labels[0]['reviewed']


def test_ocr_optional_backend_is_reported_without_fabricated_numbers(monkeypatch):
    from preprocess.auto_detect import _read_plot_annotations
    monkeypatch.setattr('shutil.which',lambda _: None)
    labels,status=_read_plot_annotations(np.full((400,600,3),255,dtype=np.uint8),100,50,500,350)
    assert labels==[] and status in ('unavailable','error:ModuleNotFoundError')
