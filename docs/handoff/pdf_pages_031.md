# YGPA-031 PDF 도면 페이지 보존

2026-09-29. 대상은 PDF 파일 순서 기준 26~29쪽이며 전체 원본은 29쪽이다. 개별 이미지 추출 대신 각 페이지 전체를 렌더링하므로 PDF에 배치된 글자·도형·그림을 함께 보존한다. 원본 PDF는 수정하거나 분할하지 않는다.

## 실행

프로젝트의 기존 requirements-extraction.txt 환경(pypdf 포함)을 사용한다. 추가 Python 패키지는 필요 없다. 렌더링에는 Poppler의 pdftoppm 실행 파일이 필요하다. 이 PC에서 확인한 경로를 명시하면 일반 PowerShell의 PATH 설정과 관계없이 실행할 수 있다.

```powershell
Set-Location -LiteralPath "C:\Users\yountae\26-2_classes\capstone"
$renderer = "C:\Users\yountae\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin\pdftoppm.exe"
.\.venv\Scripts\python.exe -B .\scripts\preserve_pdf_pages_031.py --pdftoppm $renderer --save
```

`--save` 없이 실행하면 준비 안내만 출력한다. pdftoppm이 PATH에 있다면 `--pdftoppm`은 생략할 수 있다. 다른 팀원은 자기 PC의 pdftoppm 경로를 지정한다. 실행 파일과 개인 PC 경로를 코드에 고정하거나 바이너리를 저장소에 포함하지 않는다. 실행 파일을 찾지 못하면 보류하며 자동 설치나 다운로드를 하지 않는다.

처음 실행 시 결과는 `data/processed/YGPA-031/20260927T070446904069Z/pdf-pages-v1/`에 저장된다. 해당 원본 snapshot이 아닌 새 원본을 처리할 경우 같은 문서 ID의 새 snapshot 하위 경로를 사용한다. 원본의 페이지 수가 29와 다르면 기존 페이지 선택을 그대로 적용하지 않고 보류한다.

```powershell
Invoke-Item -LiteralPath "C:\Users\yountae\26-2_classes\capstone\data\processed\YGPA-031\20260927T070446904069Z\pdf-pages-v1\review.html"
```

검토 화면에서 26·27·28·29쪽 이미지가 모두 보이는지 확인한다. ‘PNG 원본 열기’로 확대하고 원본 PDF의 같은 페이지와 비교한다. 각 페이지의 주요 구성은 사전 시각 확인에서 다음과 같았다. 이는 해당 수집본의 내용 설명이며 최신 시설 현황 확인을 뜻하지 않는다.

| PDF 파일 페이지 | 화면에서 확인할 구성 |
|---|---|
| 26 | 광양항(여수) 야적장 위치도, 여러 부두 그림과 하단 페이지 번호 |
| 27 | 광양항(광양) 야적장 위치도, 하포일반부두·컨테이너부두 그림 |
| 28 | 중마일반부두와 태인부두 도면 |
| 29 | 율촌일반부두와 율촌물양장 도면 |

## 팀 인수인계 규격

- `page-026.png`~`page-029.png`: 200 DPI로 전체 MediaBox 렌더링한 PNG. 실제 검증 환경에서 각각 1653×2337 픽셀이다. CropBox로 잘라내지 않으며 원본 PDF 회전을 렌더러가 적용한다. 이 수집본에서 MediaBox와 CropBox 차이로 인한 표시 문제는 관찰하지 못했다.
- `pages.json`: 원본 URL·snapshot·SHA-256, 파일 페이지 번호(1부터), page_index(0부터), 이미지 해시·크기, PDF 페이지 크기·회전, source_block_indices(기존 blocks.json 배열의 0부터 인덱스), existing_text를 기록한다.
- `existing_text`는 기존 추출문을 연결한 것이며 OCR 결과가 아니다. 본문·이미지의 중복 색인을 피하고, 도면의 시설명·수치와 조건은 별도로 검수해야 한다.
- `review.html`: 이미지 확대 링크 및 기존 추출문을 표시하는 로컬 검토 화면. 네트워크 요청·외부 폰트·스크립트를 포함하지 않는다.
- `validation.json`: 원본 해시, 기존 document.json/document.txt/blocks.json 해시, 출력 6개 파일의 해시, 페이지 수·선택·DPI·렌더러 버전·경고를 기록한다. review_status=page_images_saved_pending_visual_review, ocr_status=not_performed, index_approved=false를 유지한다.

원본·기존 본문을 보존한다. 검증된 원본 바이트의 임시 복사본을 렌더링하고, 4쪽이 모두 성공한 뒤 결과를 저장한다. 같은 입력·설정으로 생성된 결과의 해시가 모두 맞으면 재렌더링 없이 유지한다. 결과가 손상됐거나 입력이 바뀌면 덮어쓰지 않는다. DPI·렌더러를 바꿔 다시 만들 필요가 있으면 별도 버전 경로를 설계한다.

## 수행한 검증

실제 원본을 읽고 임시 폴더에서 전체 4쪽을 렌더링했다. Poppler 26.07.0에서 경고가 없었으며 4개 이미지의 페이지 제목·도면·하단 페이지 번호 표시를 확인했다. 도면 내부의 모든 수치·글자를 전사하거나 현행성을 검수한 것은 아니다. 페이지 연결 인덱스는 25~28이고 원본 파일 페이지는 26~29다. 원본·기존 본문 파일의 해시를 보존했고 출력 해시 및 재실행 시 건너뛰기를 확인했다.

합성 테스트 6개가 통과했다. 페이지 번호와 본문 연결, 29쪽이 아닌 원본·누락 문단 거부, 전체 페이지 렌더러 인수, PNG 검사·HTML 이스케이프, 저장·재실행·변조 탐지, 렌더링 실패 시 결과 미생성, 준비 안내에서 무저장을 확인한다. 공식 문서나 FAQ를 테스트에 복사하지 않았다.

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p "test_preserve_pdf_pages_031.py" -v
```

이 안내는 코드 준비와 임시 시험 기록이다. 사용자 실제 저장·원문 대조 완료 기록은 이후 별도로 남긴다.

## 공유 및 남은 작업

코드·합성 테스트·이 문서를 GitHub에 공유한다. 이미지·원본·파생 결과는 기존 .gitignore의 data/raw 및 data/processed 제외 범위다. 새 후보 수집이나 FAQ 접근은 없다. 청크화·검색 등록은 미진행이다. 사용자 화면 대조 후 도면 OCR/검수 범위를 정할 수 있으며, YGPA-032 특수문자·표·현행성 검토와 YGPA-030 도형 배치 미재현 항목도 남아 있다.

## 사용자 실행 및 원문 대조 확인 (2026-09-29)

사용자가 실제 실행하여 PDF 파일 26~29쪽의 PNG 4개를 저장했다. 출력 6개 파일의 해시, 기존 document.json/document.txt/blocks.json 해시, 원본 버전과 페이지 연결을 확인했다. 200 DPI, 각 1653×2337 픽셀이며 렌더러 경고는 없었다.

이후 4쪽 전체 표시, 가장자리·페이지 번호, 확대 이미지의 원문 대조 안내에 사용자가 “어 문제없어”라고 응답했다. 해당 버전의 페이지 이미지 보존 및 사용자 원문 대조 확인 완료로 기록한다. 모든 수치의 전사·현행성 검수나 검색 승인으로 확대하지 않는다.

- 원본 snapshot: 20260927T070446904069Z
- 원본 SHA-256: ddf5e36d5585b1e42ec2203a13039b796a9462adf6c49b20c33580f32da0ebcd
- 확인 결과 버전: pdf-pages-v1
- OCR·청크화·검색 등록: 미진행
- 기존 validation.json의 자동 검토 상태 및 index_approved=false는 그대로 보존한다. 이 문서가 후속 사용자 확인 기록이다.

다음 작은 검토 단위는 YGPA-032 PDF 9쪽의 U+F000 두 곳을 원본 글리프와 대조하는 작업이다. 확인 전 일괄 삭제하거나 괄호로 치환하지 않는다. 해당 문서의 표 구조·기한부 조건·현행성 검토 및 YGPA-030 도형 배치 재현은 별도 미완료 항목이다.