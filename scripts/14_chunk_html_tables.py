"""Offline HTML table restoration and draft chunks. Use --save to write sidecars."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys

prose = __import__("13_chunk_remaining")
sha = __import__("12_chunk_one", fromlist=["sha"]).sha
decode_html = __import__("04_extract_remaining", fromlist=["decode_html"]).decode_html

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'semantic-html-tables-v1'
# Raw HTML, not only flattened text, determines the cell geometry.
SOURCES = {
    'YGPA-005': ('f4d054ee4e0318e2c86fa549df749713935423df9d7ba69d14498b4939825d44', 4),
    'YGPA-009': ('bd6f8d5e765e31b64732e55c23b430fedecb6c6ce6e7a43b3c529656bb01c871', 2),
    'YGPA-010': ('9b715b3b01bf70f219aa01dc1e913d601f0432f7c0c5b980491923db5a03cfac', 1),
    'YGPA-011': ('2cfe9f9e4f34894c95ee92546c5256d4b10054cd6674d022ee127de929704367', 1),
    'YGPA-012': ('51ac5af34ce3df87c562415c5c71edf425264548fd4c36fb7667af309e8dc14b', 1),
    'YGPA-013': ('dfd5fbe34d57d5103659c0e9f9d01d8e1729ff6dac04e38193a473c01d3acc37', 1),
    'YGPA-014': ('ad89593f5010a4f80f22a106b5e38cbe760ebe7fbd6e326ae97f057db2c06cb5', 1),
    'YGPA-015': ('57f77a70f6dc5b432c3a414ee3ad53f134b4f8e508531b118b9a702edddf5b62', 1),
    'YGPA-016': ('ef2ccb445e429a72c930f88fa086465a58105859d5cef8b529b566f3eb3f098e', 1),
    'YGPA-017': ('966844146e3463d42a370e09d28a1e1c7392379130f47bf528e54d1bf8bf9964', 1),
}


class TableParser(HTMLParser):
    """Only explicit table markup is accepted; comments never become rows."""
    def __init__(self, fragment, base=0):
        super().__init__(convert_charrefs=True)
        self.fragment, self.base = fragment, base
        self.lines = [0] + [m.end() for m in re.finditer('\n',fragment)]
        self.tables = []
        self.table = self.row = self.cell = None
        self.section = 'tbody'
        self.caption = False
        self.skip = 0

    def source_offset(self):
        line, col = self.getpos()
        return self.base + self.lines[line-1] + col

    def handle_starttag(self, tag, attrs):
        if tag in ('script','style','template','noscript'):
            self.skip += 1
            return
        if self.skip:
            return
        attrs = dict(attrs)
        if tag == 'table':
            if self.table is not None:
                raise ValueError('중첩 HTML 표는 별도 검토 필요')
            self.table = dict(table_id=f'table-{len(self.tables)+1:02d}',char_start=self.source_offset(),rows=[],caption_parts=[])
        elif self.table is not None:
            if tag in ('thead','tbody','tfoot'):
                self.section = tag
            elif tag == 'caption':
                self.caption = True
            elif tag == 'tr':
                if self.row is not None:
                    raise ValueError('닫히지 않은 표 행')
                self.row = dict(section=self.section,cells=[])
            elif tag in ('td','th'):
                if self.row is None or self.cell is not None:
                    raise ValueError('표 셀 경계 오류')
                spans = {k:int(attrs.get(k,'1')) for k in ('rowspan','colspan')}
                if not (1 <= spans['rowspan'] <= 2000 and 1 <= spans['colspan'] <= 64):
                    raise ValueError('지원 범위를 벗어난 병합 셀')
                self.cell = dict(tag=tag,scope=attrs.get('scope',''),char_start=self.source_offset(),parts=[],**spans)
            elif tag in ('img','svg','object','iframe','input','select'):
                raise ValueError('표 내부 비문자 개체 검토 필요')
            elif tag in ('br','p','div','li'):
                self.handle_data(' ')

    def handle_endtag(self, tag):
        if tag in ('script','style','template','noscript'):
            self.skip = max(0,self.skip-1)
            return
        if self.skip or self.table is None:
            return
        if tag in ('td','th'):
            if self.cell is None or self.cell['tag'] != tag:
                raise ValueError('표 셀 닫힘 불일치')
            self.cell['char_end'] = self.source_offset()+len(f'</{tag}>')
            self.cell['text'] = ' '.join(''.join(self.cell.pop('parts')).split())
            self.row['cells'].append(self.cell)
            self.cell = None
        elif tag == 'tr':
            if self.row is None or self.cell is not None:
                raise ValueError('표 행 닫힘 불일치')
            self.table['rows'].append(self.row)
            self.row = None
        elif tag == 'caption':
            self.caption = False
        elif tag in ('thead','tbody','tfoot'):
            self.section = 'tbody'
        elif tag == 'table':
            if self.row is not None or self.cell is not None:
                raise ValueError('표가 완전히 닫히지 않았습니다.')
            self.table['char_end'] = self.source_offset()+len('</table>')
            self.table['caption'] = ' '.join(''.join(self.table.pop('caption_parts')).split())
            self.tables.append(self.table)
            self.table = None
        elif tag in ('p','div','li'):
            self.handle_data(' ')

    def handle_data(self, data):
        if self.skip:
            return
        if self.cell is not None:
            self.cell['parts'].append(data)
        elif self.caption and self.table is not None:
            self.table['caption_parts'].append(data)


def geometry(table):
    rows = table['rows']
    if not rows or len(rows)>2000:
        raise ValueError('빈 표 또는 과도한 행 수')
    grid, cells = {}, []
    for r, row in enumerate(rows):
        col = 0
        for cell in row['cells']:
            while (r,col) in grid:
                col += 1
            bottom, right = r+cell['rowspan'], col+cell['colspan']
            if bottom>len(rows) or right>64:
                raise ValueError('표 범위를 벗어난 병합 셀')
            if any(rows[i]['section']!=row['section'] for i in range(r,bottom)):
                raise ValueError('머리글·본문 경계를 가로지르는 병합')
            cell.update(row=r,col=col,cell_id=f"{table['table_id']}-r{r+1}c{col+1}")
            cells.append(cell)
            for rr in range(r,bottom):
                for cc in range(col,right):
                    if (rr,cc) in grid:
                        raise ValueError('병합 셀 겹침')
                    grid[rr,cc] = cell['cell_id']
            col = right
    width = max(c for r,c in grid)+1 if grid else 0
    if not width or len(grid)!=len(rows)*width:
        raise ValueError('표에 셀 누락 또는 행별 열 수 불일치')
    table['width'] = width
    table['grid'] = [[grid[r,c] for c in range(width)] for r in range(len(rows))]
    headers = [i for i,r in enumerate(rows) if r['section']=='thead']
    if headers != list(range(len(headers))):
        raise ValueError('표 머리글은 선두에 연속으로 있어야 합니다.')
    table['header_rows'] = len(headers)
    # A body group spans every connected rowspan; aggregate values appear only once.
    groups, start = [], len(headers)
    while start<len(rows):
        end = start+1
        r = start
        while r<end:
            end = max([end]+[r+c['rowspan'] for c in rows[r]['cells']])
            r += 1
        groups.append((start,end))
        start = end
    if not headers:
        groups = [(0,len(rows))]  # keep address and telephone together
    table['groups'] = groups
    return table


def parse_tables(html):
    matches = list(re.finditer(r'<!--\s*내용\s*시작\s*-->(.*?)<!--\s*내용\s*끝\s*-->',html,re.S))
    if len(matches)!=1:
        raise ValueError('본문 경계가 하나가 아닙니다.')
    match = matches[0]
    parser = TableParser(match.group(1),match.start(1))
    parser.feed(match.group(1)); parser.close()
    if parser.table is not None:
        raise ValueError('닫히지 않은 표')
    tables=[]
    for original in parser.tables:
        try:
            table=geometry(deepcopy(original))
        except ValueError as error:
            table=original
            table['geometry_error']=str(error)
            table['header_rows']=sum(r['section']=='thead' for r in table['rows'])
            table['groups']=[(table['header_rows'],len(table['rows']))]
            for r,row in enumerate(table['rows']):
                for k,cell in enumerate(row['cells']):
                    cell.update(row=r,physical_cell_index=k,cell_id=f"{table['table_id']}-r{r+1}-physical{k+1}")
        tables.append(table)
    return tables


def contexts(doc_id, table_number, doc):
    """Exact source excerpts. Do not silently drop exceptions or shared units."""
    text = doc['text']
    spans = []
    def take(start_marker, end_marker=None):
        start = text.index(start_marker)
        end = text.index(end_marker,start) if end_marker else len(text)
        spans.append(dict(kind='processed_text',char_start=start,char_end=end,text=text[start:end]))
    if doc_id=='YGPA-005' and table_number in (2,3):
        take('* 축구장 시설은','시설 사용료\n')
        take('체육시설 이용 시 유의사항\n','사용문의(')
    if doc_id=='YGPA-009' and table_number==1:
        take('※ 기상 및 선사 사정에 따라','터미널 선사 및 운항 정보로')
    if doc_id=='YGPA-012':
        take('* 소형선부두·관용선 부두 등')
    if doc_id in ('YGPA-014','YGPA-015','YGPA-016'):
        line = next(line for line in text.splitlines() if line.startswith('(단위'))
        start=text.index(line+'\n');spans.append(dict(kind='processed_text',char_start=start,char_end=start+len(line)+1,text=line+'\n'))
        if doc_id in ('YGPA-014','YGPA-016'):
            take('1단계 4번선석\n')
    return spans


def render_text(title, table, start, end, context):
    cells = {c['cell_id']:c for r in table['rows'] for c in r['cells']}
    def label(cell):
        labels=[]
        for r in range(table['header_rows']):
            for col in range(cell['col'],cell['col']+cell['colspan']):
                h=cells[table['grid'][r][col]]['text']
                if h and h not in labels: labels.append(h)
        return ' / '.join(labels) or '항목'
    lines=[title,table['caption'],'행·열 번호는 원본 표 기준(1부터 시작). 병합 값은 해당 범위에 공통이며 행별로 합산하지 않습니다.']
    for r in range(start,end):
        for cell in table['rows'][r]['cells']:
            rr=f"{r+1}~{r+cell['rowspan']}" if cell['rowspan']>1 else str(r+1)
            cc=f"{cell['col']+1}~{cell['col']+cell['colspan']}" if cell['colspan']>1 else str(cell['col']+1)
            lines.append(f"- 행 {rr}, 열 {cc} [{label(cell)}]: {cell['text'] or '(원문 빈칸)'}")
    for item in context:
        lines.extend(['관련 원문 조건·주석:',item['text']])
    return '\n'.join(lines)


def hold_reason(doc_id, table, start, end):
    if doc_id=='YGPA-013':
        return '원본 머리글과 본문 열 의미 불일치: 부두별 colspan=2이나 머리글은 1열, 최저(M)/수심(M)이 분리됨'
    for row in table['rows'][start:end]:
        for cell in row['cells']:
            for hour, minute in re.findall(r'(?<!\d)(\d{1,3}):(\d{1,3})(?!\d)',cell['text']):
                if len(minute)!=2 or not 0<=int(hour)<=23 or not 0<=int(minute)<=59:
                    return '원문 시각 표기 확인 필요: '+cell['text']
    return None


def prepare(root, doc_id):
    if doc_id not in SOURCES:
        raise ValueError('지원하지 않는 표 문서')
    _, base = prose.prepare(root,doc_id)  # shared source/FAQ/hash checks; no write/network
    if base['document_version']!=SOURCES[doc_id][0]:
        raise ValueError('검토한 원본 HTML 버전이 아닙니다.')
    raw_path = root/'data/raw'/doc_id/base['source_snapshot']/'source.html'
    processed = root/'data/processed'/doc_id/base['source_snapshot']
    raw=raw_path.read_bytes()
    if sha(raw)!=base['document_version']:
        raise ValueError('검증 중 원본 변경 감지')
    html, encoding = decode_html(raw)
    doc_bytes=(processed/'document.json').read_bytes()
    if sha(doc_bytes)!=base['input_hashes']['document.json']:
        raise ValueError('검증 중 본문 변경 감지')
    doc=json.loads(doc_bytes)
    tables=parse_tables(html)
    if len(tables)!=SOURCES[doc_id][1]:
        raise ValueError('검토한 활성 표 개수와 다릅니다.')
    chunks, coverage = [], []
    for number, table in enumerate(tables,1):
        context=contexts(doc_id,number,doc)
        table['context']=context
        for start,end in table['groups']:
            reason=table.get('geometry_error') or hold_reason(doc_id,table,start,end)
            body='' if reason else render_text(doc['title'],table,start,end,context)
            if len(body)>6000: reason='병합 행 묶음이 6,000자를 초과하여 별도 분할 검토 필요'
            coverage.append(dict(table_id=table['table_id'],row_start=start,row_end=end,status='held' if reason else 'chunk',reason=reason))
            if reason: continue
            selected=[c['cell_id'] for r in table['rows'][start:end] for c in r['cells']]
            headers=[c['cell_id'] for r in table['rows'][:table['header_rows']] for c in r['cells']]
            loc=dict(kind='html_table',path=raw_path.relative_to(root).as_posix(),encoding=encoding,
                     table_id=table['table_id'],char_start=table['char_start'],char_end=table['char_end'],
                     offset_unit='unicode_codepoint',newline_normalization='none',end_exclusive=True,
                     row_start=start,row_end=end,row_index_base=0,cell_ids=selected,header_cell_ids=headers)
            identity=dict(doc_id=doc_id,document_version=base['document_version'],chunking_version=VERSION,source_locator=loc,text=body)
            chunk={k:doc.get(k,'') for k in ('doc_id','document_version','source_snapshot','source_url','title','publisher',
                        'fetched_at','published_at','updated_at','date_status','date_evidence','text_sha256')}
            chunk.update(chunk_id=doc_id+'-'+sha(json.dumps(identity,ensure_ascii=False,sort_keys=True).encode())[:24],
                         chunking_version=VERSION,extraction_version='html-table-grid-v1',source_extraction_version=doc['extraction_version'],
                         text=body,chunk_text_sha256=sha(body.encode()),section_titles=[table['caption']],source_locator=loc,
                         context_locators=[{**s,'path':(processed/'document.txt').relative_to(root).as_posix(),
                           'offset_unit':'unicode_codepoint','newline_normalization':'CRLF_to_LF','end_exclusive':True} for s in context],
                         index_approved=False,review_status='draft_pending_chunk_review',
                         review_flags=['currentness_not_verified','table_only_partial_document'])
            if doc_id=='YGPA-009' and number==1:
                chunk['review_flags'].append('time_sensitive_schedule_confirm_with_operator')
            chunks.append(chunk)
    manifest={k:base[k] for k in ('doc_id','source_snapshot','document_version','policy_sha256','input_hashes')}
    manifest.update(chunking_version=VERSION,table_count=len(tables),chunk_count=len(chunks),table_row_coverage=coverage,
                    held_group_count=sum(x['status']=='held' for x in coverage),scope='active_html_tables_only',
                    review_status='draft_pending_chunk_review',index_approved=False)
    return chunks,tables,manifest


def review_html(tables, manifest):
    parts=['<!doctype html><meta charset="utf-8"><title>표 복원 검토</title>',
           '<style>body{font-family:sans-serif;margin:24px}table{border-collapse:collapse;margin:20px 0}td,th{border:1px solid #777;padding:8px;white-space:pre-wrap}th{background:#eef}p{max-width:1000px}</style>',
           '<h1>'+escape(manifest['doc_id'])+' 표 복원</h1><p>원문 빈칸은 빈칸으로 유지했습니다. 보류된 행도 대조용 표에는 보존됩니다. 검색 승인 전 초안입니다.</p>']
    for table in tables:
        if table.get('geometry_error'):
            parts.append('<p>구조 검증 보류: '+escape(table['geometry_error'])+' — 아래는 원문 병합 지정을 그대로 보여주는 대조용 표입니다.</p>')
        parts.append('<h2>'+escape(table['table_id'])+'</h2><table><caption>'+escape(table['caption'])+'</caption>')
        for row in table['rows']:
            parts.append('<tr>')
            for c in row['cells']:
                tag=c['tag']
                parts.append(f'<{tag} rowspan="{c["rowspan"]}" colspan="{c["colspan"]}" title="{escape(c["cell_id"])}">{escape(c["text"])}</{tag}>')
            parts.append('</tr>')
        parts.append('</table>')
        for s in table.get('context',[]): parts.append('<p>'+escape(s['text']).replace('\n','<br>')+'</p>')
    for item in manifest['table_row_coverage']:
        if item['status']=='held': parts.append('<p>보류: '+escape(str(item))+'</p>')
    return '\n'.join(parts)


def save(root,chunks,tables,manifest):
    encode=lambda x: json.dumps(x,ensure_ascii=False,indent=2).encode('utf8')
    outputs={'chunks.jsonl':''.join(json.dumps(c,ensure_ascii=False)+'\n' for c in chunks).encode(),
             'tables.json':encode(tables),'review.html':review_html(tables,manifest).encode(),
             'review.md':('\n\n'.join(['# '+manifest['doc_id']+' 표 청크']+[c['text'] for c in chunks])+'\n').encode()}
    expected={**manifest,'output_hashes':{k:sha(v) for k,v in outputs.items()}}
    out=root/'data/chunks'/manifest['doc_id']/manifest['source_snapshot']/VERSION
    if out.exists():
        try:
            old=json.loads((out/'manifest.json').read_bytes())
            if all(old.get(k)==v for k,v in expected.items()) and all(sha((out/k).read_bytes())==v for k,v in expected['output_hashes'].items()):
                return 'existing',out
        except (OSError,ValueError): pass
        raise ValueError('기존 표 청크가 다르거나 손상됐습니다. 덮어쓰지 않습니다.')
    outputs['manifest.json']=encode({**expected,'created_at':datetime.now(timezone.utc).isoformat()})
    out.mkdir(parents=True,exist_ok=False)
    try:
        for name,data in outputs.items(): (out/name).write_bytes(data)
    except OSError:
        for name in outputs: (out/name).unlink(missing_ok=True)
        out.rmdir();raise
    return 'saved',out


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--save',action='store_true')
    p.add_argument('--doc-ids',nargs='+',choices=sorted(SOURCES),default=sorted(SOURCES))
    args=p.parse_args(argv)
    reports=[];total=held=errors=0
    for doc_id in dict.fromkeys(args.doc_ids):
        try:
            chunks,tables,m=prepare(ROOT,doc_id)
            state,out=save(ROOT,chunks,tables,m) if args.save else ('preview',None)
            status='기존 유지' if state=='existing' else '표 청크 저장' if args.save else '미리보기'
            total+=len(chunks);held+=m['held_group_count']
            print(f'[{status}] {doc_id}: 표 {len(tables)}개, 청크 {len(chunks)}개, 보류 묶음 {m["held_group_count"]}개')
            reports.append(dict(doc_id=doc_id,state=state,chunk_count=len(chunks),held_group_count=m['held_group_count'],output=str(out) if out else None))
        except (OSError,ValueError,KeyError) as error:
            errors+=1;print(f'[오류 보류] {doc_id}: {error}')
            reports.append(dict(doc_id=doc_id,error=str(error)))
    if args.save:
        log=ROOT/'data/chunks/_runs'/('tables-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
        log.parent.mkdir(parents=True,exist_ok=True)
        log.write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf8')
        print(f'실행 기록: {log}')
    print(f'표 청크 {total}개, 보류 묶음 {held}개, 오류 {errors}건. '+('저장 완료.' if args.save else '저장하려면 --save를 추가하세요.'))
    print('원본·본문·기존 설명 청크는 보존했습니다. 임베딩·검색 등록은 수행하지 않았습니다.')
    return 1 if errors else 0


if __name__=='__main__': sys.exit(main())
