"""Offline, source-linked YGPA-001 chunk pilot. Preview by default; --save writes a draft."""
import argparse
import csv
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import sys

from collect_attachments import check_url

ROOT=Path(__file__).resolve().parents[1]
DOC_ID='YGPA-001'
VERSION='semantic-v1'
SUFFIX='사진촬영신청\n항만시설견학신청\n'


def sha(data):return hashlib.sha256(data).hexdigest()


def split_body(text):
    if not text.startswith('신청자격\n') or text.count('\n신청절차\n')!=1 or not text.endswith(SUFFIX):
        raise ValueError('시범 문서의 절/버튼 구조가 달라졌습니다. 청크 경계를 재검토하세요.')
    end=len(text)-len(SUFFIX);body=text[:end]
    steps=re.findall(r'(?m)^(\d+)\.\s+([^\n]+)$',body)
    if steps!=[('1','회원가입'),('2','신청서 작성'),('3','신청서 검토'),('4','신청서 완료')]:
        raise ValueError('신청절차 순서가 다릅니다.')
    if len(body)>1200:raise ValueError('한 청크 시범 범위보다 길어졌습니다.')
    return body,{'char_start':end,'char_end':len(text),'text':text[end:],'reason':'navigation_link_labels'}


def prepare(root):
    policy_path=root/'docs/contracts/data_separation_policy.json'
    policy_bytes=policy_path.read_bytes();policy=json.loads(policy_bytes)
    catalog=(root/policy['catalog_path']).resolve()
    if not catalog.is_relative_to(root.resolve()):raise ValueError('목록 경로가 프로젝트 밖입니다.')
    with catalog.open(encoding='utf-8-sig',newline='') as handle:
        rows=[row for row in csv.DictReader(handle) if row['doc_id']==DOC_ID]
    if len(rows)!=1:raise ValueError('문서 목록의 ID 중복 또는 누락')
    row=rows[0];check_url(row['source_url'],policy)
    raw_root=root/'data/raw'/DOC_ID
    snapshots=sorted(p for p in raw_root.iterdir() if p.is_dir())
    if not snapshots:raise ValueError('수집한 원본이 없습니다.')
    snapshot=snapshots[-1]
    if not snapshot.resolve().is_relative_to(raw_root.resolve()):raise ValueError('원본 경로 이탈')
    processed=root/'data/processed'/DOC_ID/snapshot.name
    if not processed.resolve().is_relative_to((root/'data/processed'/DOC_ID).resolve()):raise ValueError('본문 경로 이탈')
    metadata_bytes=(snapshot/'metadata.json').read_bytes();metadata=json.loads(metadata_bytes)
    doc_bytes=(processed/'document.json').read_bytes();doc=json.loads(doc_bytes)
    for item in (metadata,doc):
        if item['doc_id']!=DOC_ID or item['source_url']!=row['source_url'] or item['final_url']!=row['source_url']:
            raise ValueError('목록·원본·본문 출처 불일치')
        check_url(item['source_url'],policy);check_url(item['final_url'],policy)
    raw=(snapshot/'source.html').read_bytes()
    text_bytes=(processed/'document.txt').read_bytes();text=text_bytes.decode('utf8').replace('\r\n','\n')
    if sha(raw)!=metadata['content_sha256'] or sha(raw)!=doc['document_version']:
        raise ValueError('원본 해시 불일치')
    if sha(text.encode('utf8'))!=doc['text_sha256'] or text!=doc['text'] or doc['source_snapshot']!=snapshot.name:
        raise ValueError('본문 해시/버전 불일치')
    body,excluded=split_body(text)
    locator={'kind':'processed_text','path':(processed/'document.txt').relative_to(root).as_posix(),
             'char_start':0,'char_end':len(body),'offset_unit':'unicode_codepoint','newline_normalization':'CRLF_to_LF','end_exclusive':True,
             'line_start':1,'line_end':len(body.rstrip('\n').splitlines())}
    identity={'doc_id':DOC_ID,'document_version':sha(raw),'text_sha256':doc['text_sha256'],
              'extraction_version':doc['extraction_version'],'chunking_version':VERSION,
              'char_start':0,'char_end':len(body),'text':body}
    chunk_id=DOC_ID+'-'+sha(json.dumps(identity,sort_keys=True,ensure_ascii=False).encode('utf8'))[:24]
    chunk={'chunk_id':chunk_id,'doc_id':DOC_ID,'document_version':sha(raw),'source_snapshot':snapshot.name,
           'extraction_version':doc['extraction_version'],'chunking_version':VERSION,
           'text_sha256':doc['text_sha256'],'chunk_text_sha256':sha(body.encode('utf8')),
           'title':doc['title'],'section_titles':['신청자격','신청절차'],'text':body,'source_locator':locator,
           'source_url':doc['source_url'],'publisher':doc.get('publisher',''),'fetched_at':doc['fetched_at'],
           'published_at':doc.get('published_at',''),'updated_at':doc.get('updated_at',''),
           'date_status':doc['date_status'],'date_evidence':doc.get('date_evidence',''),
           'review_status':'draft_pending_chunk_review','index_approved':False}
    manifest={'doc_id':DOC_ID,'chunking_version':VERSION,'source_snapshot':snapshot.name,
              'document_version':sha(raw),'policy_sha256':sha(policy_bytes),
              'input_hashes':{'source.html':sha(raw),'metadata.json':sha(metadata_bytes),
                              'document.json':sha(doc_bytes),'document.txt':sha(text_bytes)},
              'chunk_count':1,'covered_characters':len(body),'source_characters':len(text),
              'excluded_spans':[excluded],'index_approved':False,
              'review_status':'draft_pending_chunk_review'}
    assert body+excluded['text']==text
    return [chunk],manifest


def save(root,chunks,manifest):
    encode=lambda value:json.dumps(value,ensure_ascii=False,indent=2).encode('utf8')
    outputs={'chunks.jsonl':(''.join(json.dumps(c,ensure_ascii=False)+'\n' for c in chunks)).encode('utf8')}
    lines=['# YGPA-001 청크 검토','', '신청자격 예외와 4단계 절차를 한 청크로 유지했습니다. 검색 등록 전 초안입니다.','']
    for c in chunks:lines.extend([f"## {c['chunk_id']}",f"출처: {c['source_url']}",'',c['text']])
    lines.extend(['## 제외 항목','이동 버튼 문구: 사진촬영신청, 항만시설견학신청. 제외한 원문 위치는 manifest.json에 기록했습니다.'])
    outputs['review.md']='\n'.join(lines).encode('utf8')
    expected={**manifest,'output_hashes':{k:sha(v) for k,v in outputs.items()}}
    out=root/'data/chunks'/DOC_ID/manifest['source_snapshot']/VERSION
    if out.exists():
        try:
            old=json.loads((out/'manifest.json').read_text(encoding='utf8'))
            if (all(old.get(k)==v for k,v in expected.items())
                and all(sha((out/k).read_bytes())==v for k,v in expected['output_hashes'].items())):
                return 'existing',out
        except (OSError,ValueError):pass
        raise ValueError('기존 청크가 다르거나 손상됐습니다. 덮어쓰지 않습니다.')
    outputs['manifest.json']=encode({**expected,'created_at':datetime.now(timezone.utc).isoformat()})
    out.mkdir(parents=True,exist_ok=False)
    try:
        for name,data in outputs.items():(out/name).write_bytes(data)
    except OSError:
        for name in outputs:(out/name).unlink(missing_ok=True)
        out.rmdir();raise
    return 'saved',out


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--save',action='store_true');args=parser.parse_args(argv)
    chunks,manifest=prepare(ROOT)
    if not args.save:
        print(f'청크 미리보기: {len(chunks)}개, 본문 {len(chunks[0]["text"])}자\n{chunks[0]["text"]}')
        print('저장하려면 --save를 추가하세요. 네트워크·임베딩·검색 등록 없음.');return
    state,out=save(ROOT,chunks,manifest)
    print(f"[{'청크 생성 완료' if state=='saved' else '기존 청크 유지'}] {DOC_ID}: {out}")
    print(f"청크 {len(chunks)}개, 본문 {manifest['covered_characters']}자, 이동 버튼 문구 2개 제외")
    print('원본·본문은 보존했습니다. 임베딩·검색 등록은 수행하지 않았습니다.')


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,ImportError) as error:sys.exit(f'청크화 보류: {error}')
