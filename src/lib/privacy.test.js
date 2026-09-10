import test from 'node:test';
import assert from 'node:assert/strict';
import { hasDirectIdentifier, maskForDisplay } from './privacy.js';

test('정형 식별자가 있으면 입력 단계에서 걸러 낸다', () => {
  for (const value of ['연락처 010-1234-5678', 'a@b.com 으로 알려주세요',
    '주민번호 900101-1234567', 'https://example.com/me 참고', 'sk-test_secret'])
    assert.ok(hasDirectIdentifier(value), value);
});

test('평범한 질문과 숫자가 많은 문장은 막지 않는다', () => {
  for (const value of ['지금 이 일을 계속 해도 될까요?', '대운은 1 11 21 31 41 51 61 71 순서인가요?',
    '1995년생인데 올해 흐름이 궁금해요', '', undefined])
    assert.ok(!hasDirectIdentifier(value), String(value));
});

test('서버 전송 원문과 별개로 화면 표시값만 마스킹한다', () => {
  const original = '전화 010-1234-5678, 메일 demo@example.com, 주민번호 900101-1234567';
  assert.equal(
    maskForDisplay(original),
    '전화 010-****-5678, 메일 d***@example.com, 주민번호 ******-*******',
  );
  assert.equal(original, '전화 010-1234-5678, 메일 demo@example.com, 주민번호 900101-1234567');
});
