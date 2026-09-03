const LANDMARK = {
  foreheadTop: 10,
  chin: 152,
  leftCheek: 234,
  rightCheek: 454,
  leftTemple: 127,
  rightTemple: 356,
  leftJaw: 172,
  rightJaw: 397,
  leftEyeOuter: 33,
  leftEyeInner: 133,
  rightEyeInner: 362,
  rightEyeOuter: 263,
  noseTip: 1,
  mouthLeft: 61,
  mouthRight: 291,
  leftBrow: 105,
  rightBrow: 334,
  leftEyeUpper: 159,
  rightEyeUpper: 386,
};

const round = (value, digits = 3) => Number(value.toFixed(digits));

function pixelPoint(landmarks, index, imageSize) {
  const point = landmarks[index];
  if (!point) throw new Error('얼굴 랜드마크 데이터가 충분하지 않아요.');
  return { x: point.x * imageSize.width, y: point.y * imageSize.height };
}

function distance(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function midpoint(a, b) {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}

function classifyFaceShape({ aspectRatio, jawRatio, foreheadRatio }) {
  if (foreheadRatio - jawRatio > 0.13 && jawRatio < 0.88) return '하트형';
  if (jawRatio > 0.91 && aspectRatio < 1.43) return '각진형';
  if (aspectRatio < 1.3 && jawRatio > 0.84) return '둥근형';
  if (aspectRatio > 1.48) return '긴 타원형';
  return '균형형';
}

export function measureFace(landmarks, imageSize) {
  if (!Array.isArray(landmarks) || landmarks.length < 468) {
    throw new Error('얼굴의 주요 지점을 충분히 찾지 못했어요. 정면 사진으로 다시 시도해 주세요.');
  }
  if (!imageSize?.width || !imageSize?.height) {
    throw new Error('사진 크기를 확인할 수 없어요.');
  }

  const p = (name) => pixelPoint(landmarks, LANDMARK[name], imageSize);
  const foreheadTop = p('foreheadTop');
  const chin = p('chin');
  const leftCheek = p('leftCheek');
  const rightCheek = p('rightCheek');
  const faceHeight = distance(foreheadTop, chin);
  const faceWidth = distance(leftCheek, rightCheek);

  if (faceHeight < 1 || faceWidth < 1) throw new Error('얼굴 크기를 계산하지 못했어요.');

  const leftEyeCenter = midpoint(p('leftEyeOuter'), p('leftEyeInner'));
  const rightEyeCenter = midpoint(p('rightEyeInner'), p('rightEyeOuter'));
  const faceCenterX = (leftCheek.x + rightCheek.x) / 2;
  const noseOffset = Math.abs(p('noseTip').x - faceCenterX) / faceWidth;
  const rollDegrees = Math.abs(Math.atan2(
    rightEyeCenter.y - leftEyeCenter.y,
    rightEyeCenter.x - leftEyeCenter.x,
  ) * 180 / Math.PI);

  const templeWidth = distance(p('leftTemple'), p('rightTemple'));
  const jawWidth = distance(p('leftJaw'), p('rightJaw'));
  const eyeWidth = (
    distance(p('leftEyeOuter'), p('leftEyeInner'))
    + distance(p('rightEyeInner'), p('rightEyeOuter'))
  ) / 2;
  const browEyeDistance = (
    distance(p('leftBrow'), p('leftEyeUpper'))
    + distance(p('rightBrow'), p('rightEyeUpper'))
  ) / 2;

  const xs = landmarks.map((point) => point.x);
  const ys = landmarks.map((point) => point.y);
  const coverage = (Math.max(...xs) - Math.min(...xs)) * (Math.max(...ys) - Math.min(...ys));
  const leftSpan = Math.abs(faceCenterX - leftCheek.x);
  const rightSpan = Math.abs(rightCheek.x - faceCenterX);
  const symmetryScore = Math.max(0, 1 - Math.abs(leftSpan - rightSpan) / faceWidth - noseOffset * 1.4);

  const values = {
    aspectRatio: faceHeight / faceWidth,
    jawRatio: jawWidth / faceWidth,
    foreheadRatio: templeWidth / faceWidth,
    eyeRatio: eyeWidth / faceWidth,
    mouthRatio: distance(p('mouthLeft'), p('mouthRight')) / faceWidth,
    browEyeRatio: browEyeDistance / faceHeight,
    symmetryScore,
    noseOffset,
    rollDegrees,
    coverage,
  };

  return {
    ...Object.fromEntries(Object.entries(values).map(([key, value]) => [key, round(value)])),
    faceShape: classifyFaceShape(values),
  };
}

export function validateFacePose(measurements) {
  const problems = [];
  if (measurements.coverage < 0.06) problems.push('얼굴이 너무 작게 보여요. 카메라에 조금 더 가까이 와 주세요.');
  if (measurements.rollDegrees > 12) problems.push('고개가 기울어져 있어요. 눈높이를 수평으로 맞춰 주세요.');
  if (measurements.noseOffset > 0.1) problems.push('얼굴이 옆으로 돌아가 있어요. 렌즈를 정면으로 바라봐 주세요.');
  return problems;
}
