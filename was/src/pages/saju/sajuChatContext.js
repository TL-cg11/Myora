/** 화면에 표시한 상담 내용을 우선 전달하고 중복 사전 데이터는 제외한다. */
export function buildSajuChatContext(result) {
  const story = result.interpretation?.narrative;
  if (!story) return JSON.stringify(result).slice(0, 8000);
  const lines = [
    `사주 원국: ${result.pillars}`, `정격: ${result.jeonggyeok}`, `용신: ${result.yongsin}`,
    `신살: ${(result.sinsal || []).join(', ')}`, story.title,
    `키워드: ${story.profile.keywords.join(', ')}`,
    ...story.overview,
    ...story.sections.flatMap((section) => [section.title, ...section.paragraphs]),
    ...story.supporting.map((item) => `${item.name}: ${item.text}`), story.notice,
  ];
  const context = lines.join('\n');
  return context.length <= 8000 ? context : `${context.slice(0, 7900)}\n(길이 제한으로 일부 세부 설명은 생략됨)`;
}
