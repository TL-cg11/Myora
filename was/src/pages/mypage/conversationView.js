export const conversationServiceMeta = {
  saju: { label: '사주', icon: '☯', path: '/saju', color: 'lilac' },
  tarot: { label: '타로', icon: '✦', path: '/tarot', color: 'pink' },
  face: { label: '관상', icon: '☾', path: '/face', color: 'blue' },
};

export function conversationDetailPath(service, readingId) {
  return `/mypage/conversations/${encodeURIComponent(service)}/${encodeURIComponent(readingId)}`;
}

export function toHistoryItem(reading) {
  const meta = conversationServiceMeta[reading.service] || conversationServiceMeta.saju;
  return {
    id: `${reading.service}-${reading.reading_id}`,
    type: reading.service,
    title: `${meta.label} 상담`,
    resultTitle: reading.result?.title || `${meta.label} 결과`,
    result: reading.result?.summary || (reading.message_count > 0
      ? `저장된 대화 ${reading.message_count}개`
      : '저장된 결과를 확인해 보세요.'),
    date: reading.created_at,
    detailPath: conversationDetailPath(reading.service, reading.reading_id),
  };
}
