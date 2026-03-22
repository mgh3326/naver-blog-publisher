# Task: Build naver-blog-publisher (Python)

네이버 블로그 자동 발행 도구. Playwright Python으로 로그인하고, 저장된 쿠키로 네이버 내부 API를 직접 호출하여 블로그 글을 발행한다.

## 핵심 아키텍처

**참고 구현**: `viruagent-cli`의 네이버 provider (Node.js/Playwright)를 Python으로 포팅.
참고 코드는 아래 Reference 섹션에 포함.

### 발행 플로우 (브라우저 없이 API 직접 호출)
1. **로그인** (1회): Playwright로 네이버 로그인 → `NID_AUT` + `NID_SES` 쿠키 JSON 파일 저장
2. **발행** (매번): 저장된 쿠키를 `requests` 세션에 로드 → HTTP API 직접 호출

### API 엔드포인트 (viruagent-cli에서 확인됨)
```
GET  /MyBlog.naver                          → blogId 추출
GET  /PostWriteFormSeOptions.naver           → Se-Authorization 토큰
GET  /PostWriteFormManagerOptions.naver      → 카테고리 목록
GET  platform.editor.naver.com/.../service_config → editorId
POST blog.upphoto.naver.com/{sessionKey}/simpleUpload → 이미지 업로드
POST upconvert.editor.naver.com/blog/html/components → HTML→SE컴포넌트 변환
POST /RabbitWrite.naver                     → 글 발행
```

## 프로젝트 구조

```
naver-blog-publisher/
├── README.md
├── pyproject.toml          # 패키지 설정 (pip install -e .)
├── requirements.txt
├── naver_blog/
│   ├── __init__.py
│   ├── auth.py             # Playwright 로그인 (ID/PW + manual 모드)
│   ├── session.py          # 쿠키 저장/로드/검증, requests 세션 생성
│   ├── api.py              # Naver Blog API 클라이언트
│   ├── editor.py           # HTML → SE Editor 컴포넌트 변환
│   ├── converter.py        # Markdown → HTML 변환
│   └── cli.py              # CLI 엔트리포인트
└── tests/
    ├── test_session.py
    ├── test_converter.py
    └── test_editor.py
```

## 상세 구현 요구사항

### 1. auth.py — Playwright 로그인

```python
# 두 가지 모드 지원
async def login(username=None, password=None, manual=False, session_path="~/.naver-blog/session.json"):
    """
    Playwright로 네이버 로그인 후 쿠키를 JSON으로 저장.
    
    auto mode: JS로 ID/PW 주입 (element.value = ...) → 로그인 버튼 클릭
    manual mode: 브라우저 열고 사용자가 직접 로그인 (QR 등) 대기 (5분 타임아웃)
    
    anti-detection:
    - navigator.webdriver = undefined
    - navigator.plugins 위장
    - locale: ko-KR, timezone: Asia/Seoul
    
    로그인 성공 판정: NID_AUT 쿠키 존재 확인
    에러 처리: 캡차, 2FA, 비밀번호 오류, 지역 차단 감지
    """
```

### 2. session.py — 쿠키 관리

```python
def save_cookies(context, session_path):
    """Playwright context에서 모든 쿠키 추출 → JSON 저장"""
    # context.cookies()는 httpOnly 쿠키도 접근 가능!
    # 도메인: naver.com, nid.naver.com, blog.naver.com
    
def load_session(session_path) -> requests.Session:
    """JSON에서 쿠키 로드 → requests.Session 반환"""
    # NID_AUT, NID_SES 존재 확인
    
def validate_session(session_path) -> bool:
    """세션 유효성 검증 (MyBlog.naver 접근 테스트)"""
```

### 3. api.py — Naver Blog API

viruagent-cli의 `naverApiClient.js`를 Python으로 포팅.

핵심 메서드:
- `init_blog()` → blogId 추출
- `get_token(category_no)` → Se-Authorization 토큰
- `get_categories()` → 카테고리 목록
- `upload_image(image_path, token)` → 이미지 업로드 (FormData)
- `publish_post(title, components, category_no, tags, open_type)` → RabbitWrite.naver

세션 만료 감지: 응답에 '로그인' 또는 'login' 포함 시 예외 발생.

### 4. editor.py — SE 컴포넌트

- `html_to_components(html, blog_id)` → 네이버 upconvert API 호출
- `create_image_component(img_data)` → 이미지 SE 컴포넌트 생성
- `create_title_component(title)` → 제목 SE 컴포넌트

### 5. converter.py — MD → HTML

- `md_to_html(md_content)` → (title, html, images[]) 반환
- 첫 번째 `#` 라인 = 제목
- 이미지 경로 추출 (로컬 파일만)
- 테이블 스타일 적용

### 6. cli.py — CLI

```bash
# 로그인
naver-blog login                    # 환경변수에서 ID/PW 읽기
naver-blog login --manual           # 수동 로그인 (브라우저 열림)

# 세션 확인
naver-blog auth-status

# 카테고리 조회
naver-blog categories

# 발행
naver-blog publish post.md --category 8 --tags "AI,분석" --private

# 글 목록
naver-blog list-posts --limit 10
```

## 환경 설정

```bash
# 환경변수 (선택)
NAVER_USERNAME=xxx
NAVER_PASSWORD=xxx
NAVER_SESSION_PATH=~/.naver-blog/session.json
NAVER_BLOG_ID=mgh3326    # 자동 감지도 가능
```

## 의존성

```
playwright>=1.40
requests>=2.31
markdown>=3.5
click>=8.0       # CLI
```

## 주의사항

- RPi5 (arm64)에서 실행됨 — Playwright chromium이 arm64 지원하는지 확인
- 기본 세션 경로: `~/.naver-blog/session.json`
- User-Agent: Chrome 131 Mac (viruagent-cli와 동일)
- 이미지 업로드: multipart/form-data
- 모든 API 호출 시 적절한 Referer 헤더 필수
- open_type: 0=비공개, 2=공개

## Reference: viruagent-cli 네이버 코어 코드

### auth.js (로그인)
```javascript
const ANTI_DETECTION_SCRIPT = `
  Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
  Object.defineProperty(navigator, 'languages', { get: () => ['ko-KR', 'ko', 'en-US', 'en'] });
  window.chrome = { runtime: {} };
`;

// ID/PW는 JS value 직접 주입 (fill/type 대신 봇 탐지 우회)
await page.evaluate((id) => {
  const el = document.getElementById('id');
  if (el) el.value = id;
}, resolvedUsername);

await page.evaluate((pw) => {
  const el = document.getElementById('pw');
  if (el) el.value = pw;
}, resolvedPassword);

// "로그인 상태 유지" 체크
const keepCheck = await page.$('#keep');
if (keepCheck) await keepCheck.click();

// 로그인 버튼 클릭
await page.$('#log.login').click();
```

### session.js (쿠키 관리)
```javascript
const NAVER_COOKIE_DOMAINS = ['https://www.naver.com', 'https://nid.naver.com', 'https://blog.naver.com'];

const persistNaverSession = async (context, targetSessionPath) => {
  const allCookies = [];
  for (const domain of NAVER_COOKIE_DOMAINS) {
    const cookies = await context.cookies(domain);
    allCookies.push(...cookies);
  }
  // Deduplicate by name+domain, save as JSON
};
```

### naverApiClient.js (API — 핵심)
```javascript
// blogId 추출
const initBlog = async () => {
  const html = await requestText(`${BLOG_HOST}/MyBlog.naver`, { headers });
  const match = html.match(/blogId\s*=\s*'([^']+)'/);
  blogId = match[1];
};

// Se-Authorization 토큰
const getToken = async (categoryNo) => {
  const json = await requestJson(
    `${BLOG_HOST}/PostWriteFormSeOptions.naver?blogId=${id}&categoryNo=${categoryNo}`,
    { headers: { Referer: `${BLOG_HOST}/PostWriteForm.naver?blogId=${id}&categoryNo=${categoryNo}` } }
  );
  return json.result.token;
};

// 발행
const publishPost = async ({ title, content, categoryNo, tags, openType }) => {
  const body = new URLSearchParams({
    blogId: id,
    documentModel: JSON.stringify(documentModel),
    populationParams: JSON.stringify(populationParams),
    productApiVersion: 'v1',
  });
  const response = await fetch(`${BLOG_HOST}/RabbitWrite.naver`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded', Cookie, Referer },
    body: body.toString(),
  });
};

// 이미지 업로드
const uploadImage = async (imageBuffer, filename, token) => {
  const sessionKey = await getUploadSessionKey(token);
  const uploadUrl = `https://blog.upphoto.naver.com/${sessionKey}/simpleUpload/0?userId=${id}&extractExif=true&...`;
  const formData = new FormData();
  formData.append('image', blob, filename);
  const response = await fetch(uploadUrl, { method: 'POST', headers: { Cookie }, body: formData });
  // XML 응답에서 url, width, height 파싱
};

// HTML → SE 컴포넌트
const convertHtmlToComponents = async (html) => {
  const wrappedHtml = `<html>\n<body>\n<!--StartFragment-->\n${html}\n<!--EndFragment-->\n</body>\n</html>`;
  const response = await fetch(
    `https://upconvert.editor.naver.com/blog/html/components?documentWidth=886&userId=${id}`,
    { method: 'POST', headers: { 'Content-Type': 'text/html; charset=utf-8', Cookie }, body: wrappedHtml }
  );
  return response.json();
};
```

### RabbitWrite documentModel 구조
```json
{
  "documentId": "",
  "document": {
    "version": "2.9.0",
    "theme": "default",
    "language": "ko-KR",
    "id": "<editorId>",
    "components": [
      { "@ctype": "documentTitle", "title": [...], "layout": "default", "align": "left" },
      // ... content components from upconvert
    ]
  }
}
```

### populationParams 구조
```json
{
  "configuration": {
    "openType": 2,
    "commentYn": true,
    "searchYn": true,
    "sympathyYn": true,
    "scrapType": 2,
    "outSideAllowYn": true
  },
  "populationMeta": {
    "categoryId": "8",
    "logNo": null,
    "tags": "tag1,tag2",
    "postWriteTimeType": "now"
  },
  "editorSource": "blogpc001"
}
```
