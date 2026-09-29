"""Offline draft chunks for HTML documents 002–020; preview unless --save."""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from chunk_one import sha
from collect_attachments import check_url

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'semantic-html-v1'
# Reviewed extraction hashes. Changed snapshots need a new boundary review.
REVIEWED = {
    'YGPA-002': 'd96434be779bc29c350d8534b273e81c16e8586abcf765d0f4fec4a689a88448',
    'YGPA-003': 'e6dcbff37c0afdf2a338d07e8dc8fb9a7edd4b54a7d4b0e62069c73f81d42f78',
    'YGPA-004': 'e8805a319de1d5b31b500ad2516901b6c531ba4c3911620e5cbd2f7e6fc259eb',
    'YGPA-005': '5f8ba35cb3a9df496e5e2427ab36d3391be4f94c7d36e71a33b356e76ff5a28f',
    'YGPA-006': 'c7b20daf883ee877de298799ae1f943618abac56e798838108144d534d97cf03',
    'YGPA-007': '4c4a9c893e26e08f7a896e82dacb616737b5ba3aefecd8d5371dd0494d5797fc',
    'YGPA-008': '224a315322253ec257a77c428bfd32e94226cae61ece0b09ff4df3715d6ef03f',
    'YGPA-009': 'c4fef7a5321c14dbc082b03b691a8e34d7c608d6b835d20606c8981ae1806928',
    'YGPA-010': '82440091153b2e9607b0ba477caf8552ad8b42478b5dfbb111d5e2b94842e5c3',
    'YGPA-011': 'd421e6d46d1cd41c8b8ed70ef23791d789f8d06fec95153720355cabfa9955fd',
    'YGPA-012': 'e902c85bc588fc1176d18426fc8f2b364838c5f994fc9cdcb2a8746bafb67540',
    'YGPA-013': '653fed9722aa442ce6eb5b0424d3ce9ce678e40f14232c397eff29f897ed8f7e',
    'YGPA-014': 'f7ffba4f73dcf59bb0d6a6f4c25e7089140d06b848259ffc328afb41e989445a',
    'YGPA-015': '7c713be76ee76357f730af9bdad43faa103602d37514fa009f996bf64359a4c1',
    'YGPA-016': 'a94c010ab5875585356d0f95911b544750fad8ec9fb2dc6b23cecceed80043d3',
    'YGPA-017': 'fb419bd90a4b789d948112bbc33fe7451a6e09daed51b531ee9fea652ce07497',
    'YGPA-018': '12d461e499e850252a5a509b91bd684166d4d6346c322000de866356f2b2bea7',
    'YGPA-019': '40a76993ef16e862a3d7d4ae52d3bc94a7eb248409526535144f3654b4db2460',
    'YGPA-020': '244175025d177db012a7b58e8f3189159ffa84365248f2f3a97b06f172c6f906',
}
HELD = {'YGPA-002': 'image_flowchart_branch_review', **{
    f'YGPA-{n:03d}': 'html_table_relationships_pending' for n in range(9, 14)}}


def ranges(doc_id, text):
    """Return complete, ordered source coverage: chunk, held, or excluded spans."""
    n = int(doc_id[-3:])
    if doc_id in HELD:
        return [{'char_start': 0, 'char_end': len(text), 'status': 'held', 'reason': HELD[doc_id]}]
    def at(line):
        marker = line + '\n'
        hits = [i for i in range(len(text)) if (i == 0 or text[i-1] == '\n') and text.startswith(marker, i)]
        if len(hits) != 1:
            raise ValueError(f'절 경계가 중복되거나 없습니다: {line}')
        return hits[0]
    selected = []
    def add(start, end, title):
        selected.append((start, end, title))
    if n == 3:
        add(0, len(text), '신청자격 및 발급 절차')
    elif n == 4:
        add(at('건설공사기성실적증명서'), len(text), '공개 증명서 종류')
    elif n == 5:
        # Keep operating exception and booking deadline together, then all conduct rules.
        start = text.index('* 축구장 시설은', at('이용시간'))
        add(start, at('시설 사용료'), '운영 예외 및 예약 기한')
        add(at('체육시설 이용 시 유의사항'), at('사용문의(여수광양항만관리㈜ 배후단지팀)'), '이용 시 유의사항')
        add(at('사용문의(여수광양항만관리㈜ 배후단지팀)'), at('첨부파일'), '사용 신청 방법')
    elif n == 6:
        add(at('1계정 당 하루 최대 2시간, 1개 코트만 예약 가능합니다.'), at('- 예약가능'), '계정별 예약 제한')
    elif n in (7, 8):
        warning = '※ 정부의 자원안보 위기 주의단계 경보 발령에 따라, 경보 해제 시까지 '
        start = text.index(warning)
        add(start, len(text), '예약 제한 및 이용 안내')
    elif n in (14, 15, 16):
        add(at('부두 정보'), at('부두 제원 및 이용 현황'), '부두 정보')
    elif n == 17:
        add(at('조성배경'), at('조성현황'), '조성배경 및 기간')
    elif n == 18:
        add(at('동측철송장 현황'), len(text), '동측·서측 철송장 현황')
    elif n == 19:
        add(at('입주희망'), at('임대료 감면제도'), '입주자격 및 신청절차')
    elif n == 20:
        add(at('입주준비'), at('자유무역지역 입주계약 안내서(입주계약용) 첨부파일'), '입주계약 및 제출 서류')
    else:
        raise ValueError('지원하지 않는 HTML 문서')
    spans, cursor = [], 0
    for start, end, title in selected:
        if not cursor <= start < end <= len(text) or end-start > 1200:
            raise ValueError('청크 경계/길이 검토 필요')
        if cursor < start:
            # Only leading navigation is known to be noise; unselected content stays held.
            status = 'excluded' if cursor == 0 and n != 5 else 'held'
            spans.append(dict(char_start=cursor, char_end=start, status=status,
                              reason='navigation_or_decorative_prefix' if status == 'excluded' else 'unselected_content_pending'))
        body = text[start:end]
        if '\n| ' in '\n'+body:
            raise ValueError('평탄화된 표가 설명 청크에 섞여 있습니다.')
        spans.append(dict(char_start=start, char_end=end, status='chunk', section_title=title))
        cursor = end
    if cursor < len(text):
        reason = {6:'calendar_and_navigation', 19:'discount_conditions_ambiguous', 20:'attachment_link_label'}.get(n, 'html_table_and_related_content_pending')
        spans.append(dict(char_start=cursor, char_end=len(text), status='excluded' if n in (6,20) else 'held', reason=reason))
    return spans


def prepare(root, doc_id):
    if doc_id not in REVIEWED:
        raise ValueError('지원 범위는 YGPA-002~020입니다.')
    root = root.resolve()
    policy_bytes = (root/'docs/contracts/data_separation_policy.json').read_bytes()
    policy = json.loads(policy_bytes)
    catalog = (root/policy['catalog_path']).resolve()
    if not catalog.is_relative_to(root):
        raise ValueError('목록 경로 이탈')
    with catalog.open(encoding='utf-8-sig', newline='') as handle:
        rows = [r for r in csv.DictReader(handle) if r['doc_id'] == doc_id]
    if len(rows) != 1:
        raise ValueError('문서 ID 중복 또는 누락')
    url = rows[0]['source_url']
    check_url(url, policy)
    raw_root = root/'data/raw'/doc_id
    snapshots = sorted(p for p in raw_root.iterdir() if p.is_dir())
    if not snapshots:
        raise ValueError('수집 원본 없음')
    snapshot = snapshots[-1]
    processed = root/'data/processed'/doc_id/snapshot.name
    if not snapshot.resolve().is_relative_to(raw_root.resolve()) or not processed.resolve().is_relative_to((root/'data/processed'/doc_id).resolve()):
        raise ValueError('입력 경로 이탈')
    inputs = {'source.html': (snapshot/'source.html').read_bytes(),
              'metadata.json': (snapshot/'metadata.json').read_bytes(),
              'document.json': (processed/'document.json').read_bytes(),
              'document.txt': (processed/'document.txt').read_bytes()}
    metadata, doc = json.loads(inputs['metadata.json']), json.loads(inputs['document.json'])
    for item in (metadata, doc):
        if item['doc_id'] != doc_id or item['source_url'] != url or item['final_url'] != url:
            raise ValueError('목록·원본·본문 출처 불일치')
        check_url(item['source_url'], policy)
        check_url(item['final_url'], policy)
    text = inputs['document.txt'].decode('utf8').replace('\r\n','\n')
    if sha(inputs['source.html']) != metadata['content_sha256'] or metadata['content_sha256'] != doc['document_version']:
        raise ValueError('원본 해시 불일치')
    if sha(text.encode('utf8')) != doc['text_sha256'] or text != doc['text'] or doc['source_snapshot'] != snapshot.name:
        raise ValueError('본문 해시/버전 불일치')
    if doc['text_sha256'] != REVIEWED[doc_id]:
        raise ValueError('검토한 본문 버전이 아닙니다. 새 버전의 청크 경계를 확인하세요.')
    spans = ranges(doc_id, text)
    chunks = []
    flags = ['currentness_not_verified']
    if any(s['status'] == 'held' for s in spans):
        flags.append('partial_document')
    if doc_id in ('YGPA-007','YGPA-008'):
        flags.append('temporary_reservation_restriction_included')
    for span in spans:
        start, end = span['char_start'], span['char_end']
        if span['status'] != 'chunk':
            continue
        body = text[start:end]
        identity = dict(doc_id=doc_id, document_version=doc['document_version'], text_sha256=doc['text_sha256'],
                        extraction_version=doc['extraction_version'], chunking_version=VERSION, char_start=start, char_end=end, text=body)
        chunk = {k: doc.get(k,'') for k in ('doc_id','document_version','source_snapshot','extraction_version','text_sha256',
                  'title','source_url','publisher','fetched_at','published_at','updated_at','date_status','date_evidence')}
        chunk.update(chunk_id=doc_id+'-'+sha(json.dumps(identity,sort_keys=True,ensure_ascii=False).encode('utf8'))[:24],
                     chunking_version=VERSION, chunk_text_sha256=sha(body.encode('utf8')), text=body,
                     section_titles=[span['section_title']], review_flags=flags,
                     review_status='draft_pending_chunk_review', index_approved=False,
                     source_locator=dict(kind='processed_text',path=(processed/'document.txt').relative_to(root).as_posix(),
                       char_start=start,char_end=end,offset_unit='unicode_codepoint',newline_normalization='CRLF_to_LF',
                       end_exclusive=True,line_start=text[:start].count('\n')+1,line_end=text[:end].rstrip('\n').count('\n')+1))
        chunks.append(chunk)
    manifest = dict(doc_id=doc_id,chunking_version=VERSION,source_snapshot=snapshot.name,document_version=doc['document_version'],
                    policy_sha256=sha(policy_bytes),input_hashes={k:sha(v) for k,v in inputs.items()},
                    chunk_count=len(chunks),source_characters=len(text),covered_characters=sum(len(c['text']) for c in chunks),
                    coverage_spans=spans,review_status='draft_pending_chunk_review' if chunks else 'held',index_approved=False)
    return chunks, manifest


def save(root, chunks, manifest):
    encode = lambda x: json.dumps(x,ensure_ascii=False,indent=2).encode('utf8')
    lines = [f"# {manifest['doc_id']} 청크 검토",'', '검색 승인 전 초안입니다. 보류 범위는 이번 청크에 포함되지 않습니다.','']
    for c in chunks:
        lines.extend([f"## {c['section_titles'][0]}",f"출처: {c['source_url']}",'',c['text']])
    lines.extend(['## 원문 범위 처리','', '문자 위치는 CRLF를 LF로 바꾼 본문 기준이며 끝 위치는 포함하지 않습니다.'])
    for s in manifest['coverage_spans']:
        lines.append(f"- {s['char_start']}:{s['char_end']} — {s['status']} — {s.get('reason',s.get('section_title'))}")
    outputs = {'chunks.jsonl': ''.join(json.dumps(c,ensure_ascii=False)+'\n' for c in chunks).encode('utf8'),
               'review.md': '\n'.join(lines).encode('utf8')}
    expected = {**manifest,'output_hashes':{k:sha(v) for k,v in outputs.items()}}
    out = root/'data/chunks'/manifest['doc_id']/manifest['source_snapshot']/VERSION
    if out.exists():
        try:
            old = json.loads((out/'manifest.json').read_bytes())
            if all(old.get(k)==v for k,v in expected.items()) and all(sha((out/k).read_bytes())==v for k,v in expected['output_hashes'].items()):
                return 'existing', out
        except (OSError,ValueError):
            pass
        raise ValueError('기존 출력이 다르거나 손상됐습니다. 덮어쓰지 않습니다.')
    outputs['manifest.json'] = encode({**expected,'created_at':datetime.now(timezone.utc).isoformat()})
    out.mkdir(parents=True,exist_ok=False)
    try:
        for name, data in outputs.items():
            (out/name).write_bytes(data)
    except OSError:
        for name in outputs:
            (out/name).unlink(missing_ok=True)
        out.rmdir()
        raise
    return 'saved', out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--save',action='store_true')
    parser.add_argument('--doc-ids',nargs='+',choices=sorted(REVIEWED),default=sorted(REVIEWED))
    args = parser.parse_args(argv)
    reports, total, errors = [], 0, 0
    for doc_id in dict.fromkeys(args.doc_ids):
        try:
            chunks, manifest = prepare(ROOT,doc_id)
            state, out = save(ROOT,chunks,manifest) if args.save else ('preview',None)
            held = sum(s['status']=='held' for s in manifest['coverage_spans'])
            total += len(chunks)
            status = '보류' if not chunks else ('기존 유지' if state=='existing' else '청크 생성 완료' if args.save else '미리보기')
            print(f'[{status}] {doc_id}: 청크 {len(chunks)}개, 보류 범위 {held}개')
            reports.append(dict(doc_id=doc_id,status=status,chunk_count=len(chunks),held_spans=held,output=str(out) if out else None))
        except (OSError,ValueError,KeyError) as error:
            errors += 1
            print(f'[오류 보류] {doc_id}: {error}')
            reports.append(dict(doc_id=doc_id,status='error',error=str(error)))
    if args.save:
        log = ROOT/'data/chunks/_runs'/('html-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
        log.parent.mkdir(parents=True,exist_ok=True)
        log.write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf8')
        print(f'실행 기록: {log}')
    print(f'대상 {len(reports)}건, 청크 {total}개, 오류 {errors}건. '+('저장 완료.' if args.save else '저장하려면 --save를 추가하세요.'))
    print('원본·본문·YGPA-001 청크는 보존했습니다. 임베딩·검색 등록은 수행하지 않았습니다.')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
