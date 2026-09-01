import { FaceLandmarker, FilesetResolver } from '@mediapipe/tasks-vision';

const WASM_ROOT = '/mediapipe/wasm';
const MODEL_PATH = '/mediapipe/models/face_landmarker.task';
let landmarkerPromise;

async function createLandmarker() {
  const vision = await FilesetResolver.forVisionTasks(WASM_ROOT);
  return FaceLandmarker.createFromOptions(vision, {
    baseOptions: { modelAssetPath: MODEL_PATH, delegate: 'CPU' },
    runningMode: 'IMAGE',
    numFaces: 2,
    minFaceDetectionConfidence: 0.65,
    minFacePresenceConfidence: 0.65,
    minTrackingConfidence: 0.5,
  });
}

export function getFaceLandmarker() {
  if (!landmarkerPromise) {
    landmarkerPromise = createLandmarker().catch((error) => {
      landmarkerPromise = undefined;
      throw error;
    });
  }
  return landmarkerPromise;
}

export async function detectSingleFace(image) {
  let result;
  try {
    result = (await getFaceLandmarker()).detect(image);
  } catch (error) {
    console.error('MediaPipe face detection failed', error);
    throw new Error('얼굴 분석 모델을 불러오지 못했어요. 인터넷 연결 후 새로고침해 주세요.');
  }

  const faces = result.faceLandmarks || [];
  if (faces.length === 0) {
    throw new Error('사진에서 얼굴을 찾지 못했어요. 밝은 곳에서 정면 얼굴이 잘 보이게 촬영해 주세요.');
  }
  if (faces.length > 1) {
    throw new Error('한 명의 얼굴만 나온 사진을 사용해 주세요.');
  }
  return faces[0];
}
