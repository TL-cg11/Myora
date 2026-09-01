import { copyFile, mkdir, rm, stat, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const packageWasmDir = join(projectRoot, 'node_modules', '@mediapipe', 'tasks-vision', 'wasm');
const publicRoot = join(projectRoot, 'public', 'mediapipe');
const publicWasmDir = join(publicRoot, 'wasm');
const publicModelDir = join(publicRoot, 'models');
const modelPath = join(publicModelDir, 'face_landmarker.task');
const modelUrl = 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task';
const wasmFiles = [
  'vision_wasm_internal.js',
  'vision_wasm_internal.wasm',
  'vision_wasm_nosimd_internal.js',
  'vision_wasm_nosimd_internal.wasm',
];

await mkdir(publicWasmDir, { recursive: true });
await mkdir(publicModelDir, { recursive: true });

for (const file of wasmFiles) {
  await copyFile(join(packageWasmDir, file), join(publicWasmDir, file));
}

// FilesetResolver의 기본 모드는 module 변형을 사용하지 않습니다.
for (const unusedFile of ['vision_wasm_module_internal.js', 'vision_wasm_module_internal.wasm']) {
  await rm(join(publicWasmDir, unusedFile), { force: true });
}

let modelIsReady = false;
try {
  modelIsReady = (await stat(modelPath)).size > 1_000_000;
} catch {
  modelIsReady = false;
}

if (!modelIsReady) {
  const response = await fetch(modelUrl);
  if (!response.ok) {
    throw new Error(`얼굴 모델 다운로드 실패: HTTP ${response.status}`);
  }
  const modelBuffer = Buffer.from(await response.arrayBuffer());
  if (modelBuffer.length < 1_000_000) {
    throw new Error('다운로드한 얼굴 모델 파일이 올바르지 않습니다.');
  }
  await writeFile(modelPath, modelBuffer);
}

console.log('MediaPipe 얼굴 분석 파일 준비 완료');
