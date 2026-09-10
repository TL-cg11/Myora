# 관상 기능

MediaPipe Face Landmarker를 브라우저에서 실행합니다. 선택하거나 촬영한 얼굴 사진과 468개 랜드마크 좌표는 서버로 업로드하지 않습니다. 브라우저에서 만든 측정 비율만 `/api/face/readings`로 보내며, 서버가 DB의 해석 문구를 골라 결과를 만들고 `reading`, `face_reading`에 저장합니다. 결과 아래 후속 채팅은 텍스트 관상 결과와 대화 내용만 WAS를 통해 DeepSeek API에 전달합니다.

## 디렉터리

- `components/`: 사진 첨부, 카메라 권한/촬영, 입력 상태
- `services/`: 이미지 검증, 로컬 얼굴 모델 실행
- `analysis/`: 얼굴 랜드마크 비율 계산과 정면 촬영 검증
- `interpretation/`: 서버 저장 실패 전 로컬 분석 결과와 후속 설명 문장 규칙
- `__tests__/`: 해석 문장 안전장치 테스트

## DB 저장

- `reading`: 비회원 키, 결과 제목·본문, 생성 시각
- `face_reading`: 얼굴 비율 6개, 분위기, 검출기 버전, 촬영 품질 수치
- `face_shape`: 활성화된 얼굴형 코드와 기준 문구
- `face_interpretation`: 비율·윤곽·눈매·입매·조화·분위기별 세부 문구 20개

비회원 키는 브라우저에서 만든 UUID를 사용합니다. 사진 원본과 랜드마크 좌표는 요청 스키마에서 허용하지 않으며, 새 관상 기록은 마이페이지에서 다시 확인할 수 있습니다.

## 실행

```bash
npm install
npm run dev
```

DeepSeek 채팅 키는 프로젝트 루트의 `.env.example`을 참고해 `.env`에 공통으로 입력합니다. 실제 키 파일은 Git에서 제외되며 키가 브라우저 번들에 포함되지 않습니다.

```dotenv
DEEPSEEK_API_KEY=발급받은_API_키
DEEPSEEK_MODEL=deepseek-v4-flash
```

키를 입력하거나 변경한 뒤에는 `sudo systemctl restart luck-was`로 WAS를 재시작합니다.

개발 환경에서는 `vite.config.js`가 `/api` 요청을 `http://127.0.0.1:8000`의 WAS로 전달합니다. 따라서 FastAPI와 `npm run dev`를 함께 실행하면 됩니다. 다른 WAS 주소를 사용할 때만 `VITE_FACE_CHAT_API_URL`에 전체 `/api/face/chat` 주소를 지정하세요.

`postinstall`, `predev`, `prebuild` 단계에서 `scripts/prepare-face-assets.mjs`가 MediaPipe WASM 파일을 복사하고 공개 얼굴 랜드마크 모델을 내려받습니다. 생성 파일은 `public/mediapipe/`에 있고 Git에는 포함하지 않습니다.

카메라는 브라우저 보안 정책상 `localhost` 또는 HTTPS 주소에서만 사용할 수 있습니다. 입력은 JPG, PNG, WebP 형식과 10MB 이하 파일을 지원합니다.

실시간 카메라 API가 없거나 HTTP IP 주소로 접속한 환경에서는 `capture="user"` 파일 입력으로 자동 대체합니다. 이 컴퓨터에서 테스트할 때는 `http://localhost:5173/face`를 사용하고, 휴대폰 등 다른 기기에서 접속할 때는 HTTPS로 배포해야 실시간 미리보기를 사용할 수 있습니다.

## 해석 원칙

관상에는 성격·능력·건강·미래를 판별하는 과학적 근거가 없습니다. 이 기능은 얼굴 좌표의 비율을 전통 관상 표현에 연결한 오락용 콘텐츠이며, 결과와 후속 답변 모두 실제 특성을 단정하지 않도록 작성되어 있습니다.
