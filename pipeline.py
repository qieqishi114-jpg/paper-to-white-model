"""Extract explicit dimensions, record sources, and export parameterized white models."""
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

FIELDS = ('lx', 'ly', 'beam_width', 'beam_depth', 'column_x', 'column_y', 'column_height')
NUMBER = r'(\d+(?:\.\d+)?)'
UNIT = r'(mm|cm|m|毫米|厘米|米)'
MULT = {'mm':1, 'cm':10, 'm':1000, '毫米':1, '厘米':10, '米':1000}


def ocr(path):
    result = subprocess.run(['tesseract', str(path), 'stdout', '-l',
                             os.environ.get('WHITE_OCR_LANG', 'eng+chi_sim')],
                            capture_output=True, timeout=15, check=True)
    return result.stdout.decode('utf-8')


def sources(path):
    if path is None:
        return []
    ext = path.suffix.lower()
    if ext == '.pdf':
        import pymupdf
        pages = []
        with pymupdf.open(path) as pdf:
            if len(pdf) > 60:
                raise ValueError('请先截取需要复现的页，单次上限 60 页。')
            for i, page in enumerate(pdf, 1):
                text = page.get_text(sort=True)
                if not text.strip() and os.environ.get('WHITE_OCR') == '1':
                    image = path.parent / 'ocr-page.png'
                    page.get_pixmap(dpi=180).save(image)
                    text = ocr(image)
                pages.append((f'PDF 第 {i} 页',text))
        return pages
    if ext == '.docx':
        from docx import Document
        d = Document(path)
        return ([(f'Word 第 {i} 段', p.text) for i,p in enumerate(d.paragraphs,1)]
                + [(f'Word 表 {i} 第 {j} 行', ' '.join(c.text for c in row.cells))
                   for i,t in enumerate(d.tables,1) for j,row in enumerate(t.rows,1)])
    if ext == '.txt':
        return [('TXT', path.read_text(encoding='utf-8-sig'))]
    return [('图片 OCR',ocr(path))]


def candidates(text):
    for pattern, field in [(r'X\s*向半跨|X\s*half[ -]span','lx'),
                           (r'Y\s*向半跨|Y\s*half[ -]span','ly'),
                           (r'柱高|column height','column_height'),
                           (r'梁宽|beam width','beam_width'),
                           (r'梁高|beam depth','beam_depth')]:
        for m in re.finditer(r'(?:'+pattern+r')\s*[:：=取为]?\s*'+NUMBER+r'\s*'+UNIT,text,re.I):
            yield field,float(m[1])*MULT[m[2].lower()],m[0]
    for label, fields in [(r'梁截面|beam section',('beam_width','beam_depth')),
                          (r'柱截面|column section',('column_x','column_y'))]:
        for m in re.finditer(r'(?:'+label+r')\s*[:：=]?\s*'+NUMBER+r'\s*[×xX*]\s*'+NUMBER+r'\s*'+UNIT,text,re.I):
            for field,value in zip(fields,(m[1],m[2])):
                yield field,float(value)*MULT[m[3].lower()],m[0]
    for pattern,value in [(r'内柱|十字形|interior column','cross'),(r'边柱|T\s*形|edge column','tee')]:
        for m in re.finditer(pattern,text,re.I):
            yield 'layout',value,m[0]


def variants(request):
    match = re.search(r'梁高\s*(?:改成|改为|分别取|分别为)\s*([^。；;\n]+)',request)
    if not match:
        return []
    values=[float(m[1])*MULT[m[2].lower()] for m in re.finditer(NUMBER+r'\s*'+UNIT,match[1],re.I)]
    return list(dict.fromkeys(values))


def preview(source,request):
    result,notes={},[]
    for origin,blocks in [('文献',sources(source)),('用户补充',[('文字要求',request)])]:
        hits={}
        for location,text in blocks:
            for field,value,quote in candidates(text):
                hits.setdefault(field,{})[value]=(location,quote[:90])
        for field,values in hits.items():
            if len(values)>1:
                result[field]=None
                notes.append(f'{field} 有多个值，请手动确认：'+ '；'.join(f'{v}（{loc}：{q}）' for v,(loc,q) in values.items()))
            else:
                value,(loc,quote)=next(iter(values.items()))
                result[field]=value
                notes.append(f'{field} = {value}｜{origin}｜{loc}｜{quote}')
    result={key:result.get(key) for key in ('layout',*FIELDS)}
    missing=[k for k,v in result.items() if v is None]
    if missing:
        notes.append('待补参数：'+ '、'.join(missing))
    return {'parameters':{'base':result,'beam_depth_variants':variants(request),'source_notes':notes},
            'notes':notes or ['未找到可读取的标注。请补充结构类型和尺寸。'],
            'svg':sketch(result) if not missing else ''}


def validate(base):
    if base.get('layout') not in ('cross','tee'):
        raise ValueError('layout 请填 cross（十字）或 tee（T形）。')
    for key in FIELDS:
        x=base.get(key)
        if type(x) not in (int,float) or not 0<x<=100000:
            raise ValueError(f'{key} 必须是大于 0 且不超过 100000 的毫米数值。')
    if base['lx']<=base['column_x']/2 or base['ly']<=base['column_y']/2:
        raise ValueError('半跨必须大于对应的半柱宽。')


def sketch(p):
    validate(p)
    span=max(p['lx'],p['ly'])
    sx,sy=100*p['lx']/span,100*p['ly']/span
    end=125-sy if p['layout']=='cross' else 125
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 250 250">'
            f'<path d="M {125-sx} 125 H {125+sx} M 125 {end} V {125+sy}" stroke="#267078" stroke-width="7"/>'
            '<circle cx="125" cy="125" r="8" fill="#af543c"/></svg>')


def export(folder,document):
    base=document['base']
    validate(base)
    depths=document.get('beam_depth_variants',[])
    if not isinstance(depths,list) or len(depths)>8:
        raise ValueError('最多生成 8 个梁高变体。')
    items=[dict(name='base',parameters=base)]
    for i, depth in enumerate(depths,1):
        changed={**base,'beam_depth':depth}
        validate(changed)
        items.append(dict(name=f'variant_{i:02}',parameters=changed))
    document['models']=items
    with zipfile.ZipFile(folder/'white-model.zip','w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('model_parameters.json',json.dumps(document,ensure_ascii=False,indent=2))
        z.write(Path(__file__).with_name('build_cae.py'),'build_cae.py')
        for item in items:
            z.writestr(item['name']+'.svg',sketch(item['parameters']))
        z.writestr('使用.txt','解压后在当前目录运行 abaqus cae noGUI=build_cae.py。\n生成可编辑 CAE 几何装配。毫米制，无网格、材料、荷载和分析步。\n')


def main():
    folder,source,mode=sys.argv[1:]
    folder=Path(folder)
    request=(folder/'request.txt').read_text(encoding='utf-8')
    try:
        if mode=='preview':
            result=preview(Path(source) if source else None,request)
        else:
            export(folder,json.loads((folder/'parameters.json').read_text(encoding='utf-8')))
            result={'ok':True}
    except (ValueError,KeyError,TypeError,OSError,ImportError,subprocess.SubprocessError) as exc:
        result={'error':str(exc)}
    print(json.dumps(result,ensure_ascii=True))


if __name__=='__main__':
    main()
