import assert from 'node:assert/strict';
import test from 'node:test';
import { measureFace, validateFacePose } from '../analysis/faceMeasurements.js';
import { answerFaceFollowUp } from '../interpretation/faceFollowUp.js';
import { createFaceReading } from '../interpretation/faceReadingRules.js';

const baseMeasurements = {
  faceShape: '균형형',
  aspectRatio: 1.39,
  jawRatio: 0.87,
  foreheadRatio: 0.88,
  eyeRatio: 0.185,
  mouthRatio: 0.35,
  symmetryScore: 0.95,
};

test('관상 해석은 제목, 본문, 키워드를 만든다', () => {
  const reading = createFaceReading(baseMeasurements, '밝은');
  assert.match(reading.title, /인상/);
  assert.match(reading.result, /얼굴형/);
  assert.match(reading.result, /재미용 콘텐츠/);
  assert.match(reading.title, /밝은 분위기/);
  assert.deepEqual(reading.keywords, ['#균형있는인상', '#밝은분위기', '#안정적인조화']);
});

test('허용되지 않은 인상 키워드는 안전한 기본값으로 바꾼다', () => {
  const reading = createFaceReading(baseMeasurements, '모르는 값');
  assert.ok(reading.keywords.includes('#차분한분위기'));
});

test('같은 얼굴형이어도 세부 비율과 분위기에 따라 결과가 달라진다', () => {
  const calm = createFaceReading({
    ...baseMeasurements,
    aspectRatio: 1.32,
    eyeRatio: 0.17,
    mouthRatio: 0.31,
    symmetryScore: 0.9,
  }, '차분한');
  const bright = createFaceReading({
    ...baseMeasurements,
    aspectRatio: 1.46,
    eyeRatio: 0.21,
    mouthRatio: 0.39,
    symmetryScore: 0.98,
  }, '밝은');

  assert.notEqual(calm.title, bright.title);
  assert.notEqual(calm.result, bright.result);
  assert.notDeepEqual(calm.keywords, bright.keywords);
  assert.match(calm.result, /세로와 가로 폭의 차이가 크지 않아/);
  assert.match(bright.result, /세로 흐름이 비교적 길게/);
});

test('모든 얼굴형 규칙이 단정적인 실제 성격 판단을 피한다', () => {
  for (const faceShape of ['하트형', '각진형', '둥근형', '긴 타원형', '균형형']) {
    const reading = createFaceReading({ ...baseMeasurements, faceShape });
    assert.match(reading.result, /전통|옛 관상|관상식/);
    assert.match(reading.result, /실제 성격·능력·건강·미래를 판단할 수는 없어요/);
  }
});

test('후속 질문은 관상으로 실제 성격이나 미래를 단정하지 않는다', () => {
  const reading = createFaceReading(baseMeasurements, '차분한');
  assert.match(answerFaceFollowUp(reading, '내 연애운과 성격을 알려줘'), /알 수는 없어요/);
  assert.match(answerFaceFollowUp(reading, '얼굴형을 더 설명해줘'), /사진 한 장/);
});

test('랜드마크 비율을 픽셀 기준으로 계산하고 촬영 각도를 검사한다', () => {
  const landmarks = Array.from({ length: 478 }, () => ({ x: 0.5, y: 0.5, z: 0 }));
  const set = (index, x, y) => { landmarks[index] = { x, y, z: 0 }; };
  set(10, 0.5, 0.2); set(152, 0.5, 0.8);
  set(234, 0.3, 0.5); set(454, 0.7, 0.5);
  set(127, 0.32, 0.4); set(356, 0.68, 0.4);
  set(172, 0.34, 0.7); set(397, 0.66, 0.7);
  set(33, 0.35, 0.42); set(133, 0.45, 0.42);
  set(362, 0.55, 0.42); set(263, 0.65, 0.42);
  set(1, 0.5, 0.52); set(61, 0.42, 0.62); set(291, 0.58, 0.62);
  const measured = measureFace(landmarks, { width: 1000, height: 1000 });
  assert.equal(measured.faceShape, '긴 타원형');
  assert.equal(measured.aspectRatio, 1.5);
  assert.equal(measured.eyeRatio, 0.25);
  assert.equal('browEyeRatio' in measured, false);
  assert.deepEqual(validateFacePose(measured), []);
  assert.match(validateFacePose({ ...measured, noseOffset: 0.2 })[0], /정면/);
});
