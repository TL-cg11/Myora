import assert from 'node:assert/strict';
import test from 'node:test';
import { conversationDetailPath, toHistoryItem } from './conversationView.js';

test('대화 상세 경로에 서비스와 리딩 ID를 넣는다', () => {
  assert.equal(conversationDetailPath('tarot', 42), '/mypage/conversations/tarot/42');
});

test('통합 목록 응답을 마이페이지 카드 형식으로 바꾼다', () => {
  const item = toHistoryItem({
    service: 'face',
    reading_id: 7,
    created_at: '2026-09-11T10:00:00',
    result: { title: '차분한 인상', summary: '안정적인 흐름이에요.' },
    message_count: 2,
  });

  assert.deepEqual(item, {
    id: 'face-7',
    type: 'face',
    title: '관상 상담',
    resultTitle: '차분한 인상',
    result: '안정적인 흐름이에요.',
    date: '2026-09-11T10:00:00',
    detailPath: '/mypage/conversations/face/7',
  });
});

test('요약이 없으면 대화 개수를 안내한다', () => {
  const item = toHistoryItem({
    service: 'saju', reading_id: 3, created_at: '2026-09-11T10:00:00',
    result: {}, message_count: 4,
  });
  assert.equal(item.result, '저장된 대화 4개');
});
