"""Restore remaining collected HWP tables offline; preview unless --restore."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from collect_attachments import select_targets
from restore_tables_one import HWP_IDS, restore

ROOT = Path(__file__).resolve().parents[1]
REMAINING_IDS = tuple(doc_id for doc_id in HWP_IDS if doc_id != 'YGPA-021')


def run_batch(root, targets, policy):
    results = []
    for row in targets:
        doc_id = row['doc_id']
        try:
            if doc_id not in REMAINING_IDS:
                raise ValueError('이번 배치의 대상 HWP 문서가 아닙니다.')
            state, output, validation = restore(root, row, policy)
            results.append({'doc_id': doc_id, 'state': state, 'output': str(output),
                            'table_count': validation['table_count'],
                            'cell_count': validation['cell_count']})
            if 'inline_control_count' in validation:
                results[-1]['inline_control_count'] = validation['inline_control_count']
            label = '표 복원 완료' if state == 'saved' else '기존 표 결과 유지'
            print(f'[{label}] {doc_id}: 표 {validation["table_count"]}개, 셀 {validation["cell_count"]}개')
            if validation.get('inline_control_count'):
                print(f'  겹친 글자 개체 {validation["inline_control_count"]}개 별도 보존: {output}')
        except (OSError, ValueError, KeyError, ImportError) as error:
            results.append({'doc_id': doc_id, 'state': 'held', 'reason': str(error)})
            print(f'[보류] {doc_id}: {error}')
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restore', action='store_true', help='표 구조 복원 결과 저장')
    parser.add_argument('--doc-ids', nargs='+', choices=REMAINING_IDS, help='지정한 HWP만 처리')
    args = parser.parse_args(argv)
    policy, targets = select_targets(ROOT, doc_ids=args.doc_ids or list(REMAINING_IDS))
    for row in targets:
        print(f'{row["doc_id"]} | {row["title"]}')
    if not args.restore:
        print(f'선택: {len(targets)}건. 저장하려면 --restore를 추가하세요. 네트워크 요청 없음.')
        return 0
    log_dir = ROOT / 'data/processed/_table_restoration_runs'
    log_dir.mkdir(parents=True, exist_ok=True)
    batch_id = datetime.now(timezone.utc).strftime('tables-%Y%m%dT%H%M%S%fZ')
    log_path = log_dir / f'{batch_id}.json'
    results = run_batch(ROOT, targets, policy)
    log = {'batch_id': batch_id, 'results': results, 'index_approved': False}
    with log_path.open('x', encoding='utf-8') as stream:
        json.dump(log, stream, ensure_ascii=False, indent=2)
    counts = {state: sum(r['state'] == state for r in results) for state in ('saved', 'existing', 'held')}
    print(f'표 복원: 성공 {counts["saved"]}건, 기존 {counts["existing"]}건, 보류 {counts["held"]}건')
    print(f'실행 기록: {log_path}')
    print('기존 본문은 보존했습니다. 청크화·검색 등록은 수행하지 않았습니다.')
    return 1 if counts['held'] else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, ImportError) as error:
        sys.exit(f'표 복원 보류: {error}')
