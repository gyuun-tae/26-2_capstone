"""Offline YGPA-030 table/object preservation; original visual layout stays pending."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import html
import io
import json
from pathlib import Path
import struct
import sys

import restore_tables_one as r

ROOT = Path(__file__).resolve().parents[1]
DOC_ID = 'YGPA-030'
VERSION = 'hwp-graphics-v1'
LIMIT = 32 * 1024 * 1024


def read_bounded(ole, path):
    data = ole.openstream(path).read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError('HWP 스트림 크기 제한 초과')
    return data


def embedded_item(payload):
    if len(payload) < 6:
        raise ValueError('BinData 레코드가 잘렸습니다.')
    flags, storage_id, length = struct.unpack_from('<HHH', payload)
    if flags & 15 != 1 or (flags >> 4) & 3 == 3:
        raise ValueError('외부 링크 또는 지원하지 않는 BinData 저장 방식')
    if len(payload) != 6 + 2 * length or storage_id == 0:
        raise ValueError('BinData 이름 길이/식별자 불일치')
    extension = payload[6:].decode('utf-16le').lower()
    if extension not in ('jpg', 'jpeg', 'png'):
        raise ValueError('이번 검토는 내장 JPEG/PNG만 표시합니다.')
    return flags, storage_id, extension


def collect_assets(raw, objects):
    import olefile
    assets, outputs = {}, {}
    with olefile.OleFileIO(io.BytesIO(raw)) as ole:
        header = read_bounded(ole, 'FileHeader')
        compressed = bool(struct.unpack_from('<I', header, 36)[0] & 1)
        info_raw = read_bounded(ole, 'DocInfo')
        info = r.decompress_section(info_raw) if compressed else info_raw
        items = [p for _, _, tag, _, p in r.records(info) if tag == 18]
        for obj in objects:
            obj['image_refs'] = []
            for record in obj['records']:
                if record['tag'] != 85:
                    continue
                payload = bytes.fromhex(record['payload_hex'])
                if len(payload) < 78:
                    raise ValueError('그림 개체 속성이 잘렸습니다.')
                item_id = struct.unpack_from('<H', payload, 71)[0]
                if not 1 <= item_id <= len(items):
                    raise ValueError('그림의 BinItem 참조가 없습니다.')
                if item_id not in assets:
                    flags, storage_id, ext = embedded_item(items[item_id - 1])
                    path = f'BinData/BIN{storage_id:04X}.{ext}'
                    stream = read_bounded(ole, path)
                    mode = (flags >> 4) & 3
                    data = r.decompress_section(stream) if mode == 1 or (mode == 0 and compressed) else stream
                    valid = data.startswith(b'\xff\xd8\xff') if ext in ('jpg','jpeg') else data.startswith(b'\x89PNG\r\n\x1a\n')
                    if not valid:
                        raise ValueError('내장 그림 시그니처 불일치')
                    filename = f'image-{item_id:03}.{ext}'
                    assets[item_id] = {'bin_item_id':item_id,'storage_path':path,'filename':filename,
                                       'stored_stream_sha256':r.sha(stream),'sha256':r.sha(data),'bytes':len(data)}
                    outputs[filename] = data
                obj['image_refs'].append({'locator':record['locator'],'bin_item_id':item_id,
                                          'filename':assets[item_id]['filename']})
    return list(assets.values()), outputs


def graphic_objects(tables):
    result = []
    for table in tables:
        for cell in table['cells']:
            for obj in cell.get('graphic_objects', []):
                obj['table_id'], obj['cell_id'] = table['table_id'], cell['cell_id']
                obj['record_bytes_sha256'] = r.sha(b''.join(bytes.fromhex(v['raw_record_hex']) for v in obj['records']))
                obj['record_tag_counts'] = dict(Counter(str(v['tag']) for v in obj['records']))
                result.append(obj)
    return result


def render_graphics(objects, assets):
    parts = ['<!doctype html><html lang="ko"><meta charset="utf-8"><title>YGPA-030 그림·도형 검토</title>',
             '<style>body{font-family:"Malgun Gothic",sans-serif;max-width:1000px;margin:32px auto;padding:16px;line-height:1.6}img{max-width:100%;height:auto;border:1px solid #aaa}.note{padding:16px;background:#fff1d5}li{margin:6px 0}pre{white-space:pre-wrap}</style>',
             '<h1>YGPA-030 그림·도형·글상자 검토</h1><p class="note">자료 보존 화면입니다. 아래 이미지는 원본에 내장된 그림만 보여줍니다. 그 위에 얹힌 선·도형·글상자의 배치를 재현하지 않았습니다. 이 화면으로 정박지 위치나 경계를 판단하지 마세요. 원본 지면 대조가 필요합니다.</p>',
             '<p><a href="tables.html">표 화면으로 돌아가기</a></p>']
    by_name = {a['filename']:a for a in assets}
    for obj in objects:
        parts.append(f'<section id="{html.escape(obj["object_id"],quote=True)}"><h2>{html.escape(obj["object_id"])}</h2>')
        parts.append('<p>연결된 셀: '+html.escape(obj['cell_id'])+'</p><h3>내장 그림 (도형 합성 전)</h3>')
        for name in dict.fromkeys(ref['filename'] for ref in obj['image_refs']):
            if name not in by_name:raise ValueError('화면의 이미지 연결 누락')
            parts.append(f'<img src="{html.escape(name,quote=True)}" alt="원본 내장 지도 이미지, 선·도형·글상자 배치 미재현">')
        parts.append('<h3>개체 내부 글상자 텍스트</h3><p>원본 기록 순서이며 화면상의 좌표·읽기 순서를 뜻하지 않습니다.</p><ul>')
        for text in obj['text_records']:
            parts.append('<li>'+html.escape(text['text'])+'</li>')
        parts.append('</ul><h3>보존한 구성</h3><ul>')
        names={76:'개체 구성',78:'선',79:'사각형',80:'타원',85:'그림'}
        for tag,name in names.items():
            count=obj['record_tag_counts'].get(str(tag),0)
            if count:parts.append(f'<li>{name}: {count}개 레코드</li>')
        parts.append('</ul><p>좌표·변환·서식은 원본 레코드 바이트와 계층으로 보존했습니다. 시각 재현·의미 검토·검색 승인은 보류 상태입니다.</p></section>')
    return ''.join(parts)+'</html>'


def restore(root, row, policy):
    if row['doc_id'] != DOC_ID:raise ValueError('YGPA-030 전용 실행입니다.')
    snapshot, meta, raw = r.validate_source(root,row,policy)
    processed = root/'data/processed'/DOC_ID/snapshot.name
    doc = json.loads((processed/'document.json').read_text(encoding='utf8'))
    block_bytes = (processed/'blocks.json').read_bytes()
    if (doc['doc_id'] != DOC_ID or doc['source_url'] != row['source_url'] or doc['document_version'] != r.sha(raw)
        or doc['blocks_sha256'] != r.sha(block_bytes) or doc['text_sha256'] != r.sha((processed/'document.txt').read_bytes())):
        raise ValueError('기존 본문과 원본 식별/해시 불일치')
    tables = r.read_tables(raw,DOC_ID,preserve_graphics=True)
    if len(tables) != doc['extraction_details']['table_count']:raise ValueError('표 개수 불일치')
    objects = graphic_objects(tables)
    if not objects:raise ValueError('보존할 그리기 개체가 없습니다.')
    assets, outputs = collect_assets(raw,objects)
    linked = r.link_blocks(tables,json.loads(block_bytes))
    common = {'version':VERSION,'doc_id':DOC_ID,'source_url':row['source_url'],'source_snapshot':snapshot.name,
              'source_sha256':r.sha(raw),'index_approved':False,'visual_layout_status':'not_rendered_pending_review'}
    encode=lambda value:json.dumps(value,ensure_ascii=False,indent=2).encode('utf8')
    outputs.update({'tables.json':encode({**common,'coordinate_base':0,'tables':tables}),
                    'graphics.json':encode({**common,'objects':objects,'assets':assets}),
                    'blocks_with_tables.json':encode(linked),
                    'tables.html':r.render_tables(tables,DOC_ID).encode('utf8'),
                    'graphics.html':render_graphics(objects,assets).encode('utf8')})
    validation={**common,'created_at':datetime.now(timezone.utc).isoformat(),'input_blocks_sha256':r.sha(block_bytes),
                'table_count':len(tables),'cell_count':sum(len(t['cells']) for t in tables),
                'graphic_object_count':len(objects),'graphic_record_count':sum(len(o['records']) for o in objects),
                'image_count':len(assets),'graphic_text_blocks':sum(len(o['text_records']) for o in objects),
                'mapped_text_blocks':sum(b['cell_id'] is not None for b in linked),
                'grid_coverage':'complete_no_overlap','output_hashes':{k:r.sha(v) for k,v in outputs.items()}}
    out=processed/VERSION
    if out.exists():
        try:
            old=json.loads((out/'validation.json').read_text(encoding='utf8'))
            if (old['version']==VERSION and old['doc_id']==DOC_ID and old['source_sha256']==r.sha(raw)
                and old['input_blocks_sha256']==r.sha(block_bytes) and old['output_hashes']==validation['output_hashes']
                and all(r.sha((out/name).read_bytes())==h for name,h in old['output_hashes'].items())):
                return 'existing',out,old
        except (OSError,ValueError,KeyError):pass
        raise ValueError('기존 결과가 다르거나 손상됐습니다. 덮어쓰지 않습니다.')
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
    parser.add_argument('--restore',action='store_true')
    args=parser.parse_args(argv)
    policy,targets=r.select_targets(ROOT,doc_ids=[DOC_ID])
    if not args.restore:
        print('YGPA-030 표·그림·도형 보존 준비. 저장하려면 --restore를 추가하세요. 네트워크 요청 없음.')
        return
    state,out,v=restore(ROOT,targets[0],policy)
    print(f"[{'표·개체 보존 완료' if state=='saved' else '기존 결과 유지'}] {DOC_ID}: {out}")
    print(f"표 {v['table_count']}개, 셀 {v['cell_count']}개, 그림 {v['image_count']}개, 개체 내부 문단 {v['graphic_text_blocks']}개")
    print('도형의 원본 데이터는 보존했으며 시각 배치 재현은 보류 상태입니다.')
    print('기존 본문은 보존했습니다. 청크화·검색 등록은 수행하지 않았습니다.')


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,ImportError) as error:sys.exit(f'표·개체 보존 보류: {error}')
