"""Preserve YGPA-031 PDF file pages 26-29 as full-page PNG evidence, without OCR."""
import argparse
from datetime import datetime, timezone
import html
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

from pypdf import PdfReader
from pypdf.errors import PyPdfError
from collect_attachments import select_targets
from extract_attachments import validate_source, sha

ROOT = Path(__file__).resolve().parents[1]
DOC_ID = 'YGPA-031'
VERSION = 'pdf-pages-v1'
PAGES = (26, 27, 28, 29)
DPI = 200
OUTPUT_NAMES = {'pages.json', 'review.html', *(f'page-{p:03}.png' for p in PAGES)}


def resolve_renderer(value=None):
    name = value or shutil.which('pdftoppm')
    if not name or not Path(name).is_file():
        raise ValueError('pdftoppm을 찾지 못했습니다. --pdftoppm "실행 파일의 전체 경로"를 지정하세요.')
    return str(Path(name).resolve())


def run_process(arguments):
    kwargs = {'capture_output':True, 'timeout':60, 'check':True}
    if os.name == 'nt':kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
    try:
        return subprocess.run(arguments, **kwargs)
    except subprocess.TimeoutExpired as exc:
        raise ValueError('PDF 페이지 렌더링 시간 제한 초과') from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b'').decode('utf8', errors='replace')[:500]
        raise ValueError(f'PDF 렌더러 실패: {detail}') from exc


def png_dimensions(data):
    if len(data) < 33 or data[:8] != b'\x89PNG\r\n\x1a\n' or data[12:16] != b'IHDR':
        raise ValueError('정상 PNG 페이지가 아닙니다.')
    width,height = struct.unpack_from('>II',data,16)
    if not (1 <= width <= 20000 and 1 <= height <= 20000):
        raise ValueError('PNG 페이지 크기 제한 초과')
    return width,height


def render_page(executable, source, page_number, prefix):
    result = run_process([executable,'-f',str(page_number),'-l',str(page_number),'-r',str(DPI),
                          '-png','-singlefile',str(source),str(prefix)])
    path = prefix.with_suffix('.png')
    if not path.is_file() or path.stat().st_size > 64*1024*1024:
        raise ValueError('페이지 PNG 누락 또는 크기 제한 초과')
    data = path.read_bytes()
    return data, result.stderr.decode('utf8',errors='replace').strip()


def describe_pages(raw, blocks):
    reader = PdfReader(io.BytesIO(raw),strict=True)
    if reader.is_encrypted:raise ValueError('암호화 PDF는 처리하지 않습니다.')
    if len(reader.pages) != 29:raise ValueError('확인한 29쪽 PDF와 다릅니다. 대상 페이지를 재검토해야 합니다.')
    result=[]
    for number in PAGES:
        page=reader.pages[number-1]
        linked=[i for i,b in enumerate(blocks) if b.get('locator')=={'kind':'pdf_page','page_number':number}]
        if not linked:raise ValueError(f'기존 본문에서 PDF {number}쪽의 연결 문단을 찾지 못했습니다.')
        result.append({'page_number':number,'page_index':number-1,'filename':f'page-{number:03}.png',
                       'mediabox_points':[float(x) for x in page.mediabox],
                       'cropbox_points':[float(x) for x in page.cropbox],
                       'rotation':page.rotation,'source_block_indices':linked,
                       'existing_text':'\n\n'.join(blocks[i]['text'] for i in linked),
                       'content_review_status':'pending_visual_review','ocr_status':'not_performed'})
    return result


def render_review(pages):
    parts=['<!doctype html><html lang="ko"><meta charset="utf-8"><title>YGPA-031 도면 페이지 검토</title>',
           '<style>body{font-family:"Malgun Gothic",sans-serif;max-width:1100px;margin:24px auto;padding:16px;line-height:1.6}img{max-width:100%;height:auto;border:1px solid #999}section{margin:40px 0}.note{background:#fff1d5;padding:16px}pre{white-space:pre-wrap}nav a{margin-right:20px}</style>',
           '<h1>YGPA-031 도면 4쪽 검토</h1><p class="note">원본 PDF의 파일 페이지 26~29를 전체 렌더링했습니다. 번호는 PDF 파일 순서(1부터)입니다. 이미지 저장은 OCR·수치 검수·현행성 확인·검색 승인을 뜻하지 않습니다. 작은 글씨는 PNG 원본을 열어 확대해서 원본 PDF와 비교하세요.</p><nav>']
    for page in pages:parts.append(f'<a href="#page-{page["page_number"]}">{page["page_number"]}쪽</a>')
    parts.append('</nav>')
    for page in pages:
        number=page['page_number'];filename=html.escape(page['filename'],quote=True)
        parts.append(f'<section id="page-{number}"><h2>PDF 파일 {number}쪽</h2><p><a href="{filename}" target="_blank" rel="noopener">PNG 원본 열기</a> · {page["width_pixels"]} × {page["height_pixels"]} 픽셀 · {DPI} DPI</p><img src="{filename}" alt="PDF 파일 {number}쪽 전체 페이지"><details><summary>기존에 추출된 텍스트 (도면 내부 글자 누락 가능)</summary><pre>{html.escape(page["existing_text"])}</pre></details></section>')
    return ''.join(parts)+'</html>'


def preserve(root,row,policy,renderer=None):
    if row['doc_id'] != DOC_ID:raise ValueError('YGPA-031 전용 실행입니다.')
    snapshot,meta,raw=validate_source(root,row,policy)
    if not raw.startswith(b'%PDF-'):raise ValueError('PDF 시그니처 불일치')
    processed=root/'data/processed'/DOC_ID/snapshot.name
    if not processed.resolve().is_relative_to((root/'data/processed'/DOC_ID).resolve()):
        raise ValueError('처리 경로가 문서 폴더 밖입니다.')
    doc_bytes=(processed/'document.json').read_bytes()
    doc=json.loads(doc_bytes)
    block_bytes=(processed/'blocks.json').read_bytes()
    text_bytes=(processed/'document.txt').read_bytes()
    if (doc['doc_id'] != DOC_ID or doc['source_url'] != row['source_url'] or doc['document_version'] != sha(raw)
        or doc['blocks_sha256'] != sha(block_bytes) or doc['text_sha256'] != sha(text_bytes)):
        raise ValueError('원본과 기존 추출 결과의 식별/해시 불일치')
    input_hashes={'document.json':sha(doc_bytes),'document.txt':sha(text_bytes),'blocks.json':sha(block_bytes)}
    out=processed/VERSION
    if out.exists():
        try:
            old=json.loads((out/'validation.json').read_text(encoding='utf8'))
            if (old['doc_id']==DOC_ID and old['version']==VERSION and old['source_sha256']==sha(raw)
                and old['input_hashes']==input_hashes and old['pages']==list(PAGES) and old['dpi']==DPI
                and old['index_approved'] is False and set(old['output_hashes'])==OUTPUT_NAMES
                and all(sha((out/name).read_bytes())==h for name,h in old['output_hashes'].items())):
                return 'existing',out,old
        except (OSError,ValueError,KeyError):pass
        raise ValueError('기존 도면 결과가 다르거나 손상됐습니다. 덮어쓰지 않습니다.')
    pages=describe_pages(raw,json.loads(block_bytes))
    executable=resolve_renderer(renderer)
    version_result=run_process([executable,'-v'])
    version_lines=(version_result.stdout+version_result.stderr).decode('utf8',errors='replace').splitlines()
    if not version_lines:raise ValueError('렌더러 버전 정보를 확인하지 못했습니다.')
    renderer_version=version_lines[0]
    outputs={};warnings=[]
    # Render an exact copy of the validated bytes, not a potentially changing source path.
    with tempfile.TemporaryDirectory(prefix='ygpa-031-render-') as directory:
        temp=Path(directory);source=temp/'source.pdf';source.write_bytes(raw)
        for page in pages:
            data,warning=render_page(executable,source,page['page_number'],temp/f"page-{page['page_number']:03}")
            page['width_pixels'],page['height_pixels']=png_dimensions(data)
            page['sha256']=sha(data)
            outputs[page['filename']]=data
            if warning:warnings.append({'page_number':page['page_number'],'message':warning})
    common={'doc_id':DOC_ID,'version':VERSION,'source_url':row['source_url'],'source_snapshot':snapshot.name,
            'source_sha256':sha(raw),'index_approved':False,'ocr_status':'not_performed',
            'review_status':'page_images_saved_pending_visual_review'}
    encode=lambda value:json.dumps(value,ensure_ascii=False,indent=2).encode('utf8')
    outputs['pages.json']=encode({**common,'page_number_base':1,'block_index_base':0,'dpi':DPI,
                                  'render_box':'MediaBox','pages':pages})
    outputs['review.html']=render_review(pages).encode('utf8')
    validation={**common,'created_at':datetime.now(timezone.utc).isoformat(),'source_page_count':29,
                'pages':list(PAGES),'page_image_count':len(pages),'dpi':DPI,'input_hashes':input_hashes,
                'renderer':renderer_version,'renderer_warnings':warnings,
                'output_hashes':{name:sha(data) for name,data in outputs.items()}}
    outputs['validation.json']=encode(validation)
    out.mkdir(exist_ok=False)
    try:
        for name,data in outputs.items():(out/name).write_bytes(data)
    except OSError:
        for name in outputs:(out/name).unlink(missing_ok=True)
        out.rmdir()
        raise
    return 'saved',out,validation


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--save',action='store_true')
    parser.add_argument('--pdftoppm',help='Poppler pdftoppm 실행 파일의 전체 경로')
    args=parser.parse_args(argv)
    policy,targets=select_targets(ROOT,doc_ids=[DOC_ID])
    if not args.save:
        print('YGPA-031 PDF 26~29쪽 보존 준비. 저장하려면 --save를 추가하세요. 네트워크 요청 없음.')
        return
    state,out,v=preserve(ROOT,targets[0],policy,args.pdftoppm)
    print(f"[{'도면 페이지 보존 완료' if state=='saved' else '기존 도면 결과 유지'}] {DOC_ID}: {out}")
    print(f"PDF 파일 26~29쪽, 페이지 이미지 {v['page_image_count']}개, {v['dpi']} DPI")
    if v['renderer_warnings']:print('렌더러 경고가 있습니다. validation.json을 확인하세요.')
    print('기존 본문은 보존했습니다. OCR·청크화·검색 등록은 수행하지 않았습니다.')


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,ImportError,PyPdfError) as error:sys.exit(f'도면 페이지 보존 보류: {error}')
