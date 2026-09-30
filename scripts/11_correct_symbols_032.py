"""Correct two verified PDF glyph mappings in YGPA-032, preserving the original extraction."""
import argparse
import copy
from datetime import datetime,timezone
import json
from pathlib import Path
import sys

select_targets = __import__("05_collect_attachments", fromlist=["select_targets"]).select_targets
validate_source = __import__("06_extract_attachments", fromlist=["validate_source"]).validate_source
sha = __import__("06_extract_attachments", fromlist=["sha"]).sha

ROOT=Path(__file__).resolve().parents[1]
DOC_ID='YGPA-032'
SOURCE_SHA256='a35a81c74f818b537beb1c8b3e14358a2d8f09924bdcdc54cbc79430e3938595'
VERSION='text-corrected-v1'
TITLE='무역항 등의 항만시설 사용 및 사용료 등에 관한 규정'


def correct_pair(text):
    positions=[i for i,char in enumerate(text) if char=='\uf000']
    if len(positions)!=2:raise ValueError('확인한 특수문자 두 곳과 다릅니다.')
    left,right=positions
    if ''.join(text[left+1:right].split()) != ''.join(TITLE.split()):
        raise ValueError('특수문자 사이 규정명이 다릅니다. 자동 보정을 보류합니다.')
    corrected=text[:left]+'『'+text[left+1:right]+'』'+text[right+1:]
    changes=[{'character_offset':pos,'before':'\uf000','after':replacement,
              'pdf_font':'/F7','pdf_character_code_hex':code,'basis':'source_page_9_visual_review_and_ToUnicode_collision'}
             for pos,replacement,code in ((left,'『','0003'),(right,'』','0004'))]
    return corrected,changes


def correct_blocks(blocks):
    result=copy.deepcopy(blocks)
    indices=[i for i,b in enumerate(result) if '\uf000' in b['text']]
    if len(indices)!=1 or result[indices[0]]['locator']!={'kind':'pdf_page','page_number':9}:
        raise ValueError('특수문자 위치가 확인한 PDF 9쪽 문단과 다릅니다.')
    index=indices[0]
    result[index]['text'],changes=correct_pair(result[index]['text'])
    for change in changes:change.update(block_index=index,page_number=9)
    return result,changes


def correct(root,row,policy):
    if row['doc_id']!=DOC_ID:raise ValueError('YGPA-032 전용 보정입니다.')
    snapshot,meta,raw=validate_source(root,row,policy)
    if sha(raw)!=SOURCE_SHA256:raise ValueError('대조한 원본 버전과 다릅니다. 새 원본은 재검토가 필요합니다.')
    processed=root/'data/processed'/DOC_ID/snapshot.name
    names=('document.json','document.txt','blocks.json')
    inputs={name:(processed/name).read_bytes() for name in names}
    hashes={name:sha(data) for name,data in inputs.items()}
    doc=json.loads(inputs['document.json']);blocks=json.loads(inputs['blocks.json'])
    if (doc['doc_id']!=DOC_ID or doc['source_url']!=row['source_url'] or doc['document_version']!=SOURCE_SHA256
        or doc['text_sha256']!=hashes['document.txt'] or doc['blocks_sha256']!=hashes['blocks.json']):
        raise ValueError('기존 본문/문단 또는 원본 식별 해시 불일치')
    text=inputs['document.txt'].decode('utf8')
    if doc['text']!=text:raise ValueError('메타데이터 본문과 텍스트 파일 불일치')
    out=processed/VERSION
    if out.exists():
        try:
            old=json.loads((out/'corrections.json').read_text(encoding='utf8'))
            if (old['version']==VERSION and old['source_sha256']==SOURCE_SHA256 and old['input_hashes']==hashes
                and old['index_approved'] is False and set(old['output_hashes'])==set(names)
                and all(sha((out/name).read_bytes())==h for name,h in old['output_hashes'].items())):
                return 'existing',out,old
        except (OSError,ValueError,KeyError):pass
        raise ValueError('기존 보정 결과가 다르거나 손상됐습니다. 덮어쓰지 않습니다.')
    corrected,changes=correct_blocks(blocks)
    corrected_text,text_changes=correct_pair(text)
    encode=lambda obj:json.dumps(obj,ensure_ascii=False,indent=2).encode('utf8')
    block_bytes=encode(corrected);text_bytes=corrected_text.encode('utf8')
    new_doc=copy.deepcopy(doc)
    new_doc.update(text=corrected_text,text_sha256=sha(text_bytes),blocks_sha256=sha(block_bytes),
                   blocks_path=(out/'blocks.json').relative_to(root).as_posix(),
                   correction_version=VERSION,correction_manifest=(out/'corrections.json').relative_to(root).as_posix(),
                   review_status='symbols_corrected_tables_and_currency_pending',index_approved=False)
    outputs={'document.txt':text_bytes,'blocks.json':block_bytes,'document.json':encode(new_doc)}
    report={'doc_id':DOC_ID,'version':VERSION,'source_sha256':SOURCE_SHA256,'source_snapshot':snapshot.name,
            'created_at':datetime.now(timezone.utc).isoformat(),'input_hashes':hashes,
            'block_changes':changes,'document_text_changes':text_changes,'offset_base':0,
            'changed_character_count':2,'index_approved':False,
            'basis':'PDF 9쪽 2017.02.21 부칙 규정명 양쪽의 겹낫표를 시각 대조. /F7의 0003, 0004가 모두 U+F000으로 매핑됨.',
            'remaining_review':['table_relationships','effective_dates_and_current_version'],
            'output_hashes':{name:sha(data) for name,data in outputs.items()}}
    outputs['corrections.json']=encode(report)
    out.mkdir(exist_ok=False)
    try:
        for name,data in outputs.items():(out/name).write_bytes(data)
    except OSError:
        for name in outputs:(out/name).unlink(missing_ok=True)
        out.rmdir();raise
    return 'saved',out,report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--save',action='store_true');args=parser.parse_args(argv)
    policy,rows=select_targets(ROOT,doc_ids=[DOC_ID])
    if not args.save:
        print('YGPA-032 9쪽 특수문자 두 곳 보정 준비. 저장하려면 --save를 추가하세요.');return
    state,out,report=correct(ROOT,rows[0],policy)
    print(f"[{'특수문자 보정 완료' if state=='saved' else '기존 보정 결과 유지'}] {DOC_ID}: {out}")
    print('PDF 9쪽의 U+F000 두 곳을 『 및 』로 보정했습니다.')
    print('기존 본문은 보존했습니다. 표·현행성 검토와 검색 승인은 미완료입니다.')


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,ImportError) as error:sys.exit(f'특수문자 보정 보류: {error}')
