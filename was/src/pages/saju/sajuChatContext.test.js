import test from 'node:test';
import assert from 'node:assert/strict';
import { buildSajuChatContext } from './sajuChatContext.js';

function result(text = '화면에 표시한 상담 설명') {
  return { pillars: '丙午', jeonggyeok: '건록격', yongsin: '수', sinsal: ['천을귀인'],
    interpretation: { concepts: { unused: '중복 사전' }, narrative: {
      title: '병오 이야기', profile: { keywords: ['추진력'] }, overview: [text],
      sections: [{ title: '일과 성장', paragraphs: ['전문성을 표현해 보세요'] }],
      supporting: [{ name: '천을귀인', text: '도움을 요청해 보세요' }], notice: '참고 풀이',
    } } };
}
test('화면 상담과 실제 원국을 전달하고 중복 사전을 제외한다', () => {
  const context = buildSajuChatContext(result());
  for (const value of ['丙午', '화면에 표시한 상담 설명', '전문성을 표현해 보세요', '참고 풀이']) assert.ok(context.includes(value));
  assert.ok(!context.includes('중복 사전'));
});
test('DB 문장이 길어져도 채팅 요청의 8000자 제한을 지킨다', () => {
  const context = buildSajuChatContext(result('긴 상담 내용'.repeat(2000)));
  assert.ok(context.length <= 8000);
  assert.ok(context.includes('일부 세부 설명은 생략됨'));
});
