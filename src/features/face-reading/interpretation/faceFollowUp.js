const shapeDetails = {
  '하트형': '이마와 관자 쪽의 폭에 비해 턱선이 아래로 부드럽게 모이는 비율이에요. 사진 각도와 헤어라인에 따라서도 달라 보일 수 있어요.',
  '각진형': '광대 부근과 턱 부근의 폭 차이가 비교적 작아 윤곽선이 단정하게 이어지는 비율이에요.',
  '둥근형': '얼굴의 세로 길이와 가로 폭 차이가 크지 않고 턱선이 완만하게 이어지는 비율이에요.',
  '긴 타원형': '얼굴 가로 폭에 비해 이마부터 턱까지의 세로 흐름이 조금 더 길게 보이는 비율이에요.',
  '균형형': '이마·광대·턱의 폭과 얼굴 세로 길이가 어느 한쪽으로 크게 치우치지 않은 비율이에요.',
};

function findSection(result, label) {
  return result.split('\n\n').find((paragraph) => paragraph.startsWith(`${label} ·`)) || '';
}

export function answerFaceFollowUp(reading, question) {
  const normalized = question.replace(/\s/g, '');
  if (/성격|능력|건강|수명|재물|연애운|결혼운|미래|직업/.test(normalized)) {
    return '얼굴 생김새만으로 실제 성격이나 능력, 건강, 연애·재물 같은 미래를 알 수는 없어요. 여기서는 전통 관상의 상징을 재미로만 풀어드리고 있어요. 대신 지금 결과에 나온 인상 포인트를 더 자세히 설명해 드릴 수 있어요.';
  }
  if (/얼굴형|윤곽|비율/.test(normalized)) {
    return `${reading.measurements.faceShape}으로 분류된 이유를 알려드릴게요. ${shapeDetails[reading.measurements.faceShape] || shapeDetails['균형형']} 이 분류는 사진 한 장의 좌표를 기준으로 하므로 표정과 촬영 각도에 따라 달라질 수 있어요.`;
  }
  if (/눈|눈매/.test(normalized)) return `${findSection(reading.result, '눈매')} 눈 크기로 마음이나 성격을 판단한 것은 아니고, 사진에서 보이는 얼굴 폭 대비 가로 비율만 설명한 거예요.`;
  if (/입|입매|말/.test(normalized)) return `${findSection(reading.result, '입매')} 이 역시 실제 말투나 성향을 단정하는 뜻은 아니에요.`;
  if (/사진|촬영|잘나오/.test(normalized)) {
    return '자연광이 얼굴 앞쪽에서 오게 하고, 카메라는 눈높이에 맞춰 주세요. 안경 반사나 머리카락으로 눈·턱선이 가려지지 않게 한 뒤 무표정에 가까운 편안한 표정으로 찍으면 비율을 더 안정적으로 찾을 수 있어요.';
  }
  if (/첫인상|매력|포인트|요약/.test(normalized)) {
    return `${reading.title}으로 정리할 수 있어요. ${findSection(reading.result, '전체 조화')} 다만 첫인상은 표정, 목소리, 상황에 따라 훨씬 풍부하게 달라진답니다.`;
  }
  return `현재 결과의 핵심은 “${reading.title}”이에요. 얼굴형, 눈매, 입매 중 궁금한 부분을 말해 주시면 사진에서 측정한 비율이 무엇을 뜻하는지 더 쉽게 풀어드릴게요.`;
}
