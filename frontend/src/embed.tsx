/**
 * 외부 홈페이지 삽입용 진입점.
 * host/index.html(저장한 YGPA 홈페이지) 끝에 <script type="module" src="/src/embed.tsx">로 붙인다.
 */
import { enableMocking } from './mocks/enable'
import { mountWidget } from './widget/mount'

enableMocking().then(mountWidget)
