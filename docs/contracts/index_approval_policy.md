# 색인 승인 기준 (v1.0)

결정일: 2026-10-04. 결정: 자료 담당. 실행: [`scripts/26_review_index_approval.py`](../../scripts/26_review_index_approval.py) → 승인 기록 [`data/catalog/index_approvals.json`](../../data/catalog/index_approvals.json).

청크 파일(`data/chunks`)의 `index_approved`는 처리 단계에서 늘 `false`로 만든다. 승인은 청크를 고치지 않고 **승인 기록**에 따로 남기며, 서비스용 색인은 `16_build_index.py --approved-only`로 승인 기록에서 `approved`인 청크만 넣는다.

## 결과 상태

| 상태 | 뜻 | 색인 |
|---|---|---|
| `approved` | 아래 1~4를 모두 통과 | 넣음 |
| `approved_with_notes` | 통과했지만 답변 단계에서 주의할 표시가 있음(5번 표) | 넣음 |
| `held` | 현행성 확인 실패·원문 변경·무결성 오류 | 넣지 않음. 다시 수집하거나 사람이 확인 |
| `excluded` | 원래 넣지 않는 대상 | 넣지 않음 |

## 기준

1. **출처**: 출처 URL이 `www.ygpa.or.kr` 또는 `www.law.go.kr`이고, FAQ(최종평가 전용, `data_separation_policy.json`) 경로가 아니다. FAQ면 `excluded`이고 색인 만들기를 멈춘다.
2. **제외 대상 아님**: 과거 부칙(`historical_addendum`), 더 자세한 새 수집본으로 대체된 문서(`dense.SUPERSEDED`)는 `excluded`.
3. **무결성**: 본문이 비어 있지 않고, `chunk_text_sha256`이 본문 해시와 같고, 청크가 그 문서의 **최신 수집본**에서 만들어졌다.
4. **현행성 재확인** (승인 실행 시점에 공식 출처를 다시 조회)

   | 출처 | 확인 방법 |
   |---|---|
   | 법령·고시 (LAW-) | 법령 목록 API의 현행 버전 번호와 현행 시행일이 청크와 같고, 시행일이 오늘 이전 |
   | YGPA 안내 페이지 | 지금 받은 페이지의 본문(공유 버튼 뒤 ~ '담당자 만족도 평가' 앞)이 수집본과 같음 |
   | YGPA 첨부 (HWP·PDF) | 지금 받은 파일의 SHA-256이 수집본과 같음 |
   | 부서 담당업무 (ORG-) | 지금 조회한 부서명·담당업무·전화 목록이 수집본과 같음 |

   다르면 `held`(원문 변경 → 다시 수집), 조회 실패면 `held`(확인 불가).
5. **검토 표시 처리**: 처리 단계에서 붙인 `review_flags`는 다음처럼 다룬다.

   | 표시 | 처리 | 이유 |
   |---|---|---|
   | `currentness_not_verified` | 4번 통과로 해소 | 오늘 원문과 같음을 확인 |
   | `partial_document`, `table_only_partial_document`, `appendix_material_partially_held` | 승인 | 문서의 일부만 청크로 만든 것. 청크 자체는 원문 그대로 |
   | `time_limited_items` | 승인(주의) | "…까지" 기한이 있는 조항. 지난 기한은 답변 단계(`prompt.expired_until`)에서 표시 |
   | `time_sensitive_schedule_confirm_with_operator`, `temporary_reservation_restriction_included` | 승인(주의) | 일정·예약 제한 공지. 답변 첫 문장에서 안내(지시문 8번) |
   | `manual_transcription_checked_against_pdf` | 승인(주의) | 원본 PDF와 대조해 옮겨 적은 표 |
   | `historical_provision_not_current_rule` | 제외 | 과거 부칙 |
   | `date_status: conflicting` | 승인(주의) | 페이지 날짜 표시가 서로 다를 뿐, 본문은 4번에서 오늘 원문과 같음을 확인 |

   목록에 없는 새 표시가 생기면 `held`로 두고 이 표를 갱신한 뒤 다시 실행한다.

## 유효 기간

- 승인은 **확인 시점 기준 30일** 유효하다. `--approved-only` 색인은 승인 기록이 30일을 넘었으면 만들지 않는다.
- 다시 수집하면(청크 해시가 바뀌면) 그 청크는 승인 기록과 맞지 않으므로 다시 실행해야 승인된다.
- 법령은 단계별 시행일이 지나면(예: 선박입출항법 2026-11-13) 현행 시행일이 바뀌어 `held` → 22번으로 다시 받고 승인 재실행.
