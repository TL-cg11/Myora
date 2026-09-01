import { measureFace, validateFacePose } from '../analysis/faceMeasurements.js';
import { createFaceReading } from '../interpretation/faceReadingRules.js';
import { detectSingleFace } from './faceLandmarker.js';

const MAX_FILE_SIZE = 10 * 1024 * 1024;
const SUPPORTED_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

function loadImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('사진을 열 수 없어요. JPG, PNG 또는 WebP 파일을 사용해 주세요.'));
    };
    image.src = url;
  });
}

function inspectBrightness(image) {
  const maxSide = 240;
  const scale = Math.min(1, maxSide / Math.max(image.naturalWidth, image.naturalHeight));
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
  canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
  const context = canvas.getContext('2d', { willReadFrequently: true });
  if (!context) return null;
  context.drawImage(image, 0, 0, canvas.width, canvas.height);
  const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
  let sum = 0;
  for (let index = 0; index < pixels.length; index += 4) {
    sum += pixels[index] * 0.2126 + pixels[index + 1] * 0.7152 + pixels[index + 2] * 0.0722;
  }
  return sum / (pixels.length / 4);
}

export function validateImageFile(file) {
  if (!file) throw new Error('분석할 사진을 먼저 선택해 주세요.');
  if (!SUPPORTED_TYPES.includes(file.type)) throw new Error('JPG, PNG 또는 WebP 사진만 사용할 수 있어요.');
  if (file.size > MAX_FILE_SIZE) throw new Error('사진 용량은 10MB 이하로 선택해 주세요.');
}

export async function analyzeFaceImage(file, mood) {
  validateImageFile(file);
  const image = await loadImage(file);
  if (image.naturalWidth < 320 || image.naturalHeight < 320) {
    throw new Error('사진 해상도가 너무 작아요. 가로·세로 320px 이상의 사진을 사용해 주세요.');
  }

  const brightness = inspectBrightness(image);
  if (brightness !== null && brightness < 45) throw new Error('사진이 너무 어두워요. 얼굴 앞쪽에 빛이 오도록 다시 촬영해 주세요.');
  if (brightness !== null && brightness > 245) throw new Error('사진이 너무 밝아요. 강한 역광이나 조명을 피해서 다시 촬영해 주세요.');

  const landmarks = await detectSingleFace(image);
  const measurements = measureFace(landmarks, {
    width: image.naturalWidth,
    height: image.naturalHeight,
  });
  const poseProblems = validateFacePose(measurements);
  if (poseProblems.length) throw new Error(poseProblems[0]);

  return createFaceReading(measurements, mood);
}
