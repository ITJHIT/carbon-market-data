# CBAM 계산기 웹앱

브라우저에서 EU 탄소국경세(CBAM) 비용을 추정하는 정적 웹앱. 서버 없음(모든 계산은
클라이언트 JS), 데이터 전송 없음 → 무료 정적 호스팅 + 기업 데이터 안심.

## 로컬 미리보기
`index.html`을 브라우저로 열면 끝. (더블클릭)

## Vercel 무료 배포 (l1chain과 동일 방식)
1. vercel.com 로그인 → **Add New… → Project**
2. `ITJHIT/carbon-market-data` 저장소 Import
3. **Root Directory → `web`** 로 지정 (중요: 이 폴더만 배포)
4. Framework Preset: **Other**, Build Command 비움, Output 그대로
5. **Deploy** → `https://<프로젝트명>.vercel.app` 링크 생성

→ 이 링크 하나를 수출사·컨설팅펌·링크드인에 뿌리면 영업 시작.

## 커스터마이즈
- 배출계수 기본값: `index.html`의 `EF` 객체
- CBAM 의무 반영률: `PHASE_IN` (공식 스케줄, 수정 불필요)
- 문의 메일: CTA의 `mailto:` 주소
