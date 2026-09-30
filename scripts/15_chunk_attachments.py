"""Offline attachment draft chunks: whole forms, articles across pages, explicit holds."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

select_targets = __import__("05_collect_attachments", fromlist=["select_targets"]).select_targets
check_url = __import__("05_collect_attachments", fromlist=["check_url"]).check_url
validate_source = __import__("06_extract_attachments", fromlist=["validate_source"]).validate_source
sha = __import__("06_extract_attachments", fromlist=["sha"]).sha
build_text = __import__("06_extract_attachments", fromlist=["build_text"]).build_text
validate_grid = __import__("07_restore_tables_one", fromlist=["validate_grid"]).validate_grid

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'semantic-attachments-v1'
SOURCES = dict(zip((f'YGPA-{n:03d}' for n in range(21,34)), (
    '4188a8c80da83ca1361d10a0a817be4b3ac6558712856d396693dde7bcfe5010',
    '0dec5deb7a71a962ed226b507be6e4d518fd0a1516c7f386b2c59f61e41dae55',
    'acd41cdcdfbc758a3696f2170f83e5f415976932dcc7565c4e6768a204313319',
    '2c3b59f99eeedc18cea6bea8ec7148cef65114cdf00659840e0854de547c63e0',
    '60051c7533cc3e57c3bec2da466bee5fd9cad5060397468d62fc78881fe7380a',
    'fb155e11c8bdc4495bd8cbe732bd186a934cc48557ed48d7e5dc4eca70581c7f',
    'abeebc494dcd04f171d1c45920fbe0e2e2c79442ff2600267dce4e3f24f7ea7d',
    '1bee77b582c9161556c4ccb2446e52987d93f4069840964755ecf8d1c4c04223',
    'c802ef21feed7628b202ae5eeb604a526fb691ab473792f26ac3f40326326f4e',
    '9122e2b6020614d70c248207af7c95a6036114b10a3655ffe16e16b7ac4ea0ac',
    'ddf5e36d5585b1e42ec2203a13039b796a9462adf6c49b20c33580f32da0ebcd',
    'a35a81c74f818b537beb1c8b3e14358a2d8f09924bdcdc54cbc79430e3938595',
    'f31e725f0692e6e7d8138fba0b8ca2b19223faf793faf5eede38d88a8db30c71')))
ARTICLE = re.compile(r'(?m)^[ \t]*제[ \t]*(\d+)[ \t]*조(?:[ \t]*의[ \t]*(\d+))?[ \t]*\(')
ADDENDUM = re.compile(r'(?m)^[ \t]*부[ \t]*칙[^\n]*')


def read_json(path): return json.loads(path.read_bytes())


def verify_outputs(folder, report):
    for name, expected in report['output_hashes'].items():
        path=(folder/name).resolve()
        if not path.is_relative_to(folder.resolve()) or sha(path.read_bytes())!=expected:
            raise ValueError('파생 파일 해시/경로 불일치: '+name)


def load(root, row, policy):
    doc_id=row['doc_id']
    snapshot, meta, raw=validate_source(root,row,policy)
    if sha(raw)!=SOURCES.get(doc_id): raise ValueError('검토한 첨부 원본 버전이 아닙니다.')
    folder=root/'data/processed'/doc_id/snapshot.name
    if not folder.resolve().is_relative_to((root/'data/processed'/doc_id).resolve()):
        raise ValueError('본문 경로 이탈')
    inputs={}
    def remember(path):
        data=path.read_bytes();inputs[path.relative_to(root).as_posix()]=sha(data);return data
    remember(snapshot/'metadata.json')
    doc=json.loads(remember(folder/'document.json'))
    blocks=json.loads(remember(folder/'blocks.json'));text=remember(folder/'document.txt')
    for key in ('doc_id','source_url','parent_source_url','final_url'):
        if doc[key]!=meta[key]: raise ValueError('원본·본문 식별 불일치: '+key)
    check_url(doc['source_url'],policy)
    if (doc['source_snapshot']!=snapshot.name or doc['document_version']!=sha(raw)
        or doc['blocks_sha256']!=sha((folder/'blocks.json').read_bytes()) or doc['text_sha256']!=sha(text)
        or doc['text']!=text.decode('utf8') or build_text({'blocks':blocks})!=doc['text']):
        raise ValueError('기존 본문·문단 해시/내용 불일치')
    original_folder=folder
    tables=[];linked=[]
    if doc_id=='YGPA-032':
        folder=folder/'text-corrected-v1'
        report=json.loads(remember(folder/'corrections.json'))
        if report['source_sha256']!=sha(raw) or report['version']!='text-corrected-v1':
            raise ValueError('보정 버전 불일치')
        for name,h in report['input_hashes'].items():
            if inputs.get((original_folder/name).relative_to(root).as_posix())!=h:
                raise ValueError('보정 입력 해시 불일치')
        verify_outputs(folder,report)
        doc=json.loads(remember(folder/'document.json'))
        blocks=json.loads(remember(folder/'blocks.json'));text=remember(folder/'document.txt')
        if (doc['document_version']!=sha(raw) or doc['source_snapshot']!=snapshot.name or doc['doc_id']!=doc_id
            or doc['source_url']!=row['source_url'] or doc['text_sha256']!=sha(text)
            or doc['blocks_sha256']!=sha((folder/'blocks.json').read_bytes())
            or doc['text']!=text.decode('utf8') or build_text({'blocks':blocks})!=doc['text']):
            raise ValueError('보정 본문 불일치')
    elif doc['extracted_format']=='hwp5':
        version='hwp-graphics-v1' if doc_id=='YGPA-030' else 'hwp-tables-v2' if doc_id=='YGPA-033' else 'hwp-tables-v1'
        side=folder/version
        report=json.loads(remember(side/'validation.json'))
        if report['version']!=version or report['source_sha256']!=sha(raw) or report['input_blocks_sha256']!=doc['blocks_sha256']:
            raise ValueError('표 복원 입력 불일치')
        verify_outputs(side,report)
        payload=json.loads(remember(side/'tables.json'));linked=json.loads(remember(side/'blocks_with_tables.json'))
        if payload['source_sha256']!=sha(raw) or payload['doc_id']!=doc_id: raise ValueError('표 출처 불일치')
        tables=payload['tables']
        if [(b['locator'],b['text']) for b in linked]!=[(b['locator'],b['text']) for b in blocks]:
            raise ValueError('복원 문단 연결 불일치')
        ids=set()
        for t in tables:
            validate_grid(t)
            if t['table_id'] in ids: raise ValueError('표 ID 중복')
            ids.add(t['table_id'])
        cells={c['cell_id']:c for t in tables for c in t['cells']}
        if len(cells)!=sum(len(t['cells']) for t in tables): raise ValueError('셀 ID 중복')
        for t in tables:
            if t['parent_cell_id'] is not None and t['parent_cell_id'] not in cells: raise ValueError('중첩 표 부모 누락')
            for cell in t['cells']:
                if any(child not in ids for child in cell['nested_table_ids']): raise ValueError('중첩 표 누락')
        for b in linked:
            if b.get('cell_id') and b['cell_id'] not in cells: raise ValueError('문단의 셀 누락')
        folder=side
    return doc,blocks,tables,linked,folder,inputs


def table_text(tables):
    lines=['표 좌표는 1부터 시작합니다. 병합 값은 표시 범위에 공통입니다. 빈 셀은 원본 표에 보존된 미기재 칸이며 값 0을 뜻하지 않습니다.']
    for t in tables:
        lines.append(f"표 {t['table_id']} ({t['rows']}행 × {t['columns']}열), 부모 셀: {t['parent_cell_id'] or '없음'}")
        for cell in t['cells']:
            r,c=cell['row']+1,cell['column']+1
            contents=[cell['text']] if cell['text'] else []
            contents.extend('겹친 글자: '+x['text'] for x in cell.get('inline_controls',[]))
            if cell['nested_table_ids']: contents.append('포함 표: '+', '.join(cell['nested_table_ids']))
            if cell.get('graphic_objects'): raise ValueError('시각 개체가 있는 표는 별도 보류해야 합니다.')
            if contents:
                lines.append(f"행 {r}~{r+cell['rowspan']-1}, 열 {c}~{c+cell['colspan']-1}: "+' / '.join(contents))
        lines.append(f"미기재 빈 셀 {sum(c['is_blank'] for c in t['cells'])}개 — 위치는 tables.json 참조")
    return '\n'.join(lines)


def block_refs(blocks, indices, path):
    return [dict(path=path,block_index=i,locator=blocks[i]['locator'],char_start=0,char_end=len(blocks[i]['text']),
                 offset_unit='unicode_codepoint',end_exclusive=True) for i in indices]


def split_regulation(blocks, indices, path):
    """Join page/record text for boundaries, retain exact per-block source slices."""
    parts=[];segments=[];offset=0
    for i in indices:
        text=blocks[i]['text'];parts.append(text)
        segments.append((offset,offset+len(text),i));offset+=len(text)+1
    text='\n'.join(parts)
    supplement=list(ADDENDUM.finditer(text))
    stop=supplement[0].start() if supplement else len(text)
    articles=list(ARTICLE.finditer(text[:stop]))
    if not articles: raise ValueError('조항 경계를 찾지 못했습니다.')
    ranges=[(0,articles[0].start(),'제·개정 이력','context_only')]
    for j,m in enumerate(articles):
        end=articles[j+1].start() if j+1<len(articles) else stop
        ranges.append((m.start(),end,'제'+m[1]+'조'+('의'+m[2] if m[2] else ''),'article'))
    for j,m in enumerate(supplement):
        end=supplement[j+1].start() if j+1<len(supplement) else len(text)
        ranges.append((m.start(),end,m.group().strip(),'historical_addendum'))
    result=[]
    for start,end,title,kind in ranges:
        refs=[]
        for a,b,i in segments:
            left,right=max(a,start),min(b,end)
            if left<right:
                refs.append(dict(path=path,block_index=i,locator=blocks[i]['locator'],char_start=left-a,char_end=right-a,
                                 offset_unit='unicode_codepoint',end_exclusive=True))
        if refs: result.append(dict(text=text[start:end],title=title,kind=kind,source_refs=refs))
    return result


def prepare(root,row,policy):
    doc,blocks,tables,linked,folder,inputs=load(root,row,policy)
    doc_id=doc['doc_id'];chunks=[];coverage=[]
    original=root/'data/processed'/doc_id/doc['source_snapshot']
    blockpath=(folder/'blocks.json' if doc['extracted_format']=='pdf' else original/'blocks.json').relative_to(root).as_posix()
    def emit(text,title,kind,refs,table_ids=(),context_refs=()):
        limit=12000 if kind=='whole_form' else 6000
        reason='revision_history_context' if kind=='context_only' else 'oversized_semantic_unit' if len(text)>limit else None
        entry=dict(kind=kind,title=title,source_refs=refs,table_ids=list(table_ids),status='held' if reason else 'chunk',reason=reason)
        coverage.append(entry)
        if reason:return
        locator=dict(kind='attachment_composite',source_refs=refs,table_ids=list(table_ids))
        if context_refs: locator['context_refs']=list(context_refs)
        if table_ids: locator['tables_path']=(folder/'tables.json').relative_to(root).as_posix()
        identity=dict(doc_id=doc_id,document_version=doc['document_version'],chunking_version=VERSION,source_locator=locator,text=text)
        chunk={k:doc.get(k,'') for k in ('doc_id','document_version','source_snapshot','extraction_version','text_sha256','title',
              'source_url','parent_source_url','publisher','fetched_at','published_at','updated_at','date_status','date_evidence')}
        chunk.update(chunk_id=doc_id+'-'+sha(json.dumps(identity,ensure_ascii=False,sort_keys=True).encode())[:24],
                     chunking_version=VERSION,structure_version=folder.name if tables else doc.get('correction_version','original_blocks'),
                     section_titles=[title],text=text,chunk_text_sha256=sha(text.encode()),chunk_kind=kind,source_locator=locator,
                     review_status='draft_pending_chunk_review',index_approved=False,
                     review_flags=['currentness_not_verified']
                         +(['appendix_material_partially_held'] if doc_id in ('YGPA-030','YGPA-031','YGPA-032') else [])
                         +(['historical_provision_not_current_rule'] if kind=='historical_addendum' else []))
        chunks.append(chunk);entry['chunk_id']=chunk['chunk_id']
    if doc['extracted_format']=='hwp5' and doc_id!='YGPA-030':
        outside=[i for i,b in enumerate(linked) if not b.get('cell_id')]
        if any(b.get('graphic_object_id') for b in linked): raise ValueError('미처리 도형 문단')
        body=doc['title']+'\n표 밖 안내:\n'+'\n'.join(blocks[i]['text'] for i in outside)+'\n'+table_text(tables)
        emit(body,'서식 전체: 작성 항목·안내·동의 문구','whole_form',block_refs(blocks,range(len(blocks)),blockpath),[t['table_id'] for t in tables])
    elif doc_id=='YGPA-030':
        # Reviewed raw version: prose precedes the first appendix marker.
        boundary=next(i for i,b in enumerate(blocks) if b['text'].startswith('〔별지1〕'))
        for unit in split_regulation(blocks,list(range(boundary)),blockpath):
            emit(unit['text'],unit['title'],unit['kind'],unit['source_refs'])
        context_indices=set()
        for t in tables:
            indices=[i for i,b in enumerate(linked) if b.get('table_id')==t['table_id']]
            refs=block_refs(blocks,indices,blockpath)
            if any(c.get('graphic_objects') for c in t['cells']):
                coverage.append(dict(kind='graphic_table',status='held',reason='graphic_layout_pending',table_ids=[t['table_id']],source_refs=refs))
            else:
                context=[];i=min(indices)-1
                while i>=boundary and not linked[i].get('table_id') and not linked[i].get('graphic_object_id'):
                    context.insert(0,i);i-=1
                context_indices.update(context)
                emit(doc['title']+'\n'+'\n'.join(blocks[i]['text'] for i in context)+'\n'+table_text([t]),
                     '별지 표 '+t['table_id'],'table',refs,[t['table_id']],block_refs(blocks,context,blockpath))
        other=[i for i in range(boundary,len(blocks)) if not linked[i].get('table_id')]
        coverage.append(dict(kind='appendix_labels',status='context_only',reason='included_as_table_context',source_refs=block_refs(blocks,sorted(context_indices),blockpath)))
        coverage.append(dict(kind='appendix_labels_or_graphic_text',status='held',reason='appendix_context_pending',source_refs=block_refs(blocks,[i for i in other if i not in context_indices],blockpath)))
    else:
        last=12 if doc_id=='YGPA-031' else 10
        if [b['locator'].get('page_number') for b in blocks]!=list(range(1,len(blocks)+1)):
            raise ValueError('PDF 페이지 순서 오류')
        units=split_regulation(blocks,list(range(last)),blockpath)
        expected=[str(i) for i in range(1,32 if doc_id=='YGPA-031' else 26)]
        if doc_id=='YGPA-032':expected.insert(4,'4의2')
        found=[u['title'].replace('제','').replace('조','') for u in units if u['kind']=='article']
        if found!=expected: raise ValueError('본문 조항 번호 누락/중복 또는 경계 변경')
        for unit in units:emit(unit['text'],unit['title'],unit['kind'],unit['source_refs'])
        coverage.append(dict(kind='pdf_appendix',status='held',reason='tables_drawings_and_time_limited_rates_pending',
                             source_refs=block_refs(blocks,range(last,len(blocks)),blockpath)))
    # Every source character must be accounted for exactly once, including explicit holds.
    for i,b in enumerate(blocks):
        spans=sorted((r['char_start'],r['char_end']) for e in coverage for r in e.get('source_refs',[]) if r['block_index']==i)
        cursor=0
        for start,end in spans:
            if start!=cursor or end<start: raise ValueError('본문 범위 누락 또는 중복')
            cursor=end
        if cursor!=len(b['text']): raise ValueError(f'문단 {i}의 범위 누락')
    manifest=dict(doc_id=doc_id,source_snapshot=doc['source_snapshot'],document_version=doc['document_version'],
                  chunking_version=VERSION,policy_sha256=sha((root/'docs/contracts/data_separation_policy.json').read_bytes()),
                  input_hashes=inputs,chunk_count=len(chunks),coverage=coverage,table_count=len(tables),
                  held_unit_count=sum(e['status']=='held' for e in coverage),index_approved=False)
    return chunks,manifest


def save(root,chunks,manifest):
    lines=['# '+manifest['doc_id']+' 첨부 청크 검토','검색 승인 전 초안입니다. 날짜 미확인 및 보류 항목은 manifest.json을 확인하세요.']
    for c in chunks:lines.extend(['## '+c['section_titles'][0],c['text']])
    lines.extend(['## 보류 항목']+[e['reason'] for e in manifest['coverage'] if e['status']=='held'])
    outputs={'chunks.jsonl':''.join(json.dumps(c,ensure_ascii=False)+'\n' for c in chunks).encode(),
             'review.md':'\n\n'.join(lines).encode()}
    expected={**manifest,'output_hashes':{k:sha(v) for k,v in outputs.items()}}
    out=root/'data/chunks'/manifest['doc_id']/manifest['source_snapshot']/VERSION
    if out.exists():
        old=read_json(out/'manifest.json')
        if all(old.get(k)==v for k,v in expected.items()):
            verify_outputs(out,old);return 'existing',out
        raise ValueError('기존 청크 불일치. 덮어쓰지 않습니다.')
    outputs['manifest.json']=json.dumps({**expected,'created_at':datetime.now(timezone.utc).isoformat()},ensure_ascii=False,indent=2).encode()
    out.mkdir(parents=True,exist_ok=False)
    try:
        for name,data in outputs.items():(out/name).write_bytes(data)
    except OSError:
        for name in outputs:(out/name).unlink(missing_ok=True)
        out.rmdir();raise
    return 'saved',out


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--save',action='store_true')
    p.add_argument('--doc-ids',nargs='+',choices=sorted(SOURCES),default=sorted(SOURCES));args=p.parse_args(argv)
    policy,rows=select_targets(ROOT,doc_ids=list(dict.fromkeys(args.doc_ids)))
    results=[];total=errors=0
    for row in rows:
        try:
            chunks,m=prepare(ROOT,row,policy)
            state,out=save(ROOT,chunks,m) if args.save else ('preview',None)
            total+=len(chunks)
            print(f"[{'기존 유지' if state=='existing' else '첨부 청크 저장' if args.save else '미리보기'}] {row['doc_id']}: 청크 {len(chunks)}개, 보류 단위 {m['held_unit_count']}개")
            results.append(dict(doc_id=row['doc_id'],state=state,chunk_count=len(chunks),held_unit_count=m['held_unit_count'],output=str(out) if out else None))
        except (OSError,ValueError,KeyError) as error:
            errors+=1;print(f"[오류 보류] {row['doc_id']}: {error}");results.append(dict(doc_id=row['doc_id'],error=str(error)))
    if args.save:
        log=ROOT/'data/chunks/_runs'/('attachments-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
        log.parent.mkdir(parents=True,exist_ok=True);log.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
        print(f'실행 기록: {log}')
    print(f'대상 {len(rows)}건, 첨부 청크 {total}개, 오류 {errors}건. '+('저장 완료.' if args.save else '저장하려면 --save를 추가하세요.'))
    print('원본·본문·기존 청크는 보존했습니다. 임베딩·검색 등록은 수행하지 않았습니다.')
    return 1 if errors else 0


if __name__=='__main__':sys.exit(main())
