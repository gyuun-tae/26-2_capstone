#!/usr/bin/env node
/**
 * 브라우저에서 "웹페이지, 전체"로 저장한 YGPA 홈페이지를 위젯 시연용 host/ 로 변환한다.
 *
 *   npm run prepare-host -- ~/Desktop/여수광양항만공사.html
 *
 * - host/ 는 .gitignore 대상이다 (실제 기관 페이지 복제본이므로 공개 저장소에 올리지 않는다)
 * - 이미지·영상은 원본 서버에서 불러오도록 루트 상대경로를 https://www.ygpa.or.kr 로 바꾼다
 * - 네이버 애널리틱스(wcslog)를 제거해 로컬 시연이 YGPA 방문 통계에 잡히지 않게 한다
 * - </body> 앞에 위젯 스크립트를 붙인다
 */
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { basename, dirname, extname, join, resolve } from 'node:path'

const ORIGIN = 'https://www.ygpa.or.kr'
const ANALYTICS_FILES = ['wcslog.js', 'synchronizer.js']

const input = process.argv[2]
if (!input) {
  console.error('사용법: npm run prepare-host -- <저장한 html 경로>')
  process.exit(1)
}

const htmlPath = resolve(input)
const stem = basename(htmlPath, extname(htmlPath))
// macOS는 한글 파일명을 NFD로 저장하고, HTML 안의 경로도 NFD일 수 있어 두 형태를 모두 다룬다
const dirNames = [...new Set([`${stem}_files`.normalize('NFC'), `${stem}_files`.normalize('NFD')])]
const filesDir = dirNames.map((name) => join(dirname(htmlPath), name)).find((p) => existsSync(p))
if (!filesDir) {
  console.error(`${stem}_files 폴더를 찾지 못했습니다. "웹페이지, 전체"로 저장했는지 확인하세요.`)
  process.exit(1)
}

const outDir = resolve('host')
rmSync(outDir, { recursive: true, force: true })
mkdirSync(outDir)
cpSync(filesDir, join(outDir, 'files'), { recursive: true })
for (const file of ANALYTICS_FILES) rmSync(join(outDir, 'files', file), { force: true })

let html = readFileSync(htmlPath, 'utf8')
for (const name of dirNames) html = html.replaceAll(`./${name}/`, './files/')
html = html.replace(/(src|href|poster)="\/(?!\/)/g, `$1="${ORIGIN}/`)
html = html.replace(/<script[^>]*src="\.\/files\/(?:wcslog|synchronizer)\.js"[^>]*><\/script>/g, '')
html = html.replace(/<script type="text\/javascript">\s*if\(!wcs_add\)[\s\S]*?<\/script>/, '')
html = html.replace(
  /<!DOCTYPE html>/i,
  `<!DOCTYPE html>
<!--
  로컬 시연용 복제 페이지 (scripts/prepare-host.mjs 로 생성). 공개 배포 금지.
  이미지·영상은 ${ORIGIN} 에서 불러오므로 인터넷 연결 필요. 네이버 애널리틱스 제거함.
-->`,
)
const bodyEnd = html.lastIndexOf('</body>')
if (bodyEnd === -1) {
  console.error('</body> 태그를 찾지 못했습니다.')
  process.exit(1)
}
html = `${html.slice(0, bodyEnd)}
<!-- YGPA AI 업무도우미 위젯 (Vite 개발 서버에서 로드) -->
<script type="module" src="/src/embed.tsx"></script>
${html.slice(bodyEnd)}`
writeFileSync(join(outDir, 'index.html'), html)

for (const file of readdirSync(join(outDir, 'files')).filter((f) => f.endsWith('.css'))) {
  const cssPath = join(outDir, 'files', file)
  const css = readFileSync(cssPath, 'utf8').replace(/url\((['"]?)\/(?!\/)/g, `url($1${ORIGIN}/`)
  writeFileSync(cssPath, css)
}

// 저장 시 .map 파일은 받지 않으므로 sourceMappingURL 주석을 지워 개발 서버 경고를 없앤다
for (const file of readdirSync(join(outDir, 'files')).filter((f) => /\.(js|css)$/.test(f))) {
  const filePath = join(outDir, 'files', file)
  const source = readFileSync(filePath, 'utf8')
  const cleaned = source.replace(/\/[/*][#@] sourceMappingURL=\S+(\s*\*\/)?/g, '')
  if (cleaned !== source) writeFileSync(filePath, cleaned)
}

console.log('host/ 생성 완료 → npm run dev 후 http://localhost:5173/host/')
