# 관상 기능

외부 유료 API 없이 MediaPipe Face Landmarker를 브라우저에서 실행합니다. 선택하거나 촬영한 얼굴 사진 자체는 서버로 업로드하지 않으며, 결과 문장도 브라우저의 규칙 모듈에서 생성합니다.

## 디렉터리

- `components/`: 사진 첨부, 카메라 권한/촬영, 입력 상태
- `services/`: 이미지 검증, 로컬 얼굴 모델 실행
- `analysis/`: 얼굴 랜드마크 비율 계산과 정면 촬영 검증
- `interpretation/`: 관상 결과 및 후속 설명 문장 규칙
- `__tests__/`: 해석 문장 안전장치 테스트

## 실행

```bash
npm install
npm run dev
```

`postinstall`, `predev`, `prebuild` 단계에서 `scripts/prepare-face-assets.mjs`가 MediaPipe WASM 파일을 복사하고 공개 얼굴 랜드마크 모델을 내려받습니다. 생성 파일은 `public/mediapipe/`에 있고 Git에는 포함하지 않습니다.

카메라는 브라우저 보안 정책상 `localhost` 또는 HTTPS 주소에서만 사용할 수 있습니다. 입력은 JPG, PNG, WebP 형식과 10MB 이하 파일을 지원합니다.

## 해석 원칙

관상에는 성격·능력·건강·미래를 판별하는 과학적 근거가 없습니다. 이 기능은 얼굴 좌표의 비율을 전통 관상 표현에 연결한 오락용 콘텐츠이며, 결과와 후속 답변 모두 실제 특성을 단정하지 않도록 작성되어 있습니다.
