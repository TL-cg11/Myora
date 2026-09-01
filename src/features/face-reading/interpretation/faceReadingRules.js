const shapeReadings = {
  '하트형': {
    title: '섬세한 선과 또렷한 중심이 만나는 인상',
    text: '윗부분의 여유와 아래로 모이는 윤곽이 함께 보여요. 전통 관상식 표현으로는 부드러운 감각과 분명한 집중력이 공존하는 모습으로 풀곤 해요.',
    keyword: '#섬세한윤곽',
  },
  '각진형': {
    title: '단정한 윤곽에서 안정감이 느껴지는 인상',
    text: '볼과 턱선의 폭이 비교적 고르게 이어져 전체 윤곽이 단정해 보여요. 옛 관상에서는 이런 균형을 꾸준함과 안정감의 상징으로 이야기하곤 했어요.',
    keyword: '#단정한인상',
  },
  '둥근형': {
    title: '부드러운 여백이 편안함을 주는 인상',
    text: '세로와 가로 비율이 부드럽게 어우러지고 턱선도 완만하게 보여요. 전통적인 해석에서는 친근함과 유연한 분위기를 떠올리는 윤곽이에요.',
    keyword: '#편안한윤곽',
  },
  '긴 타원형': {
    title: '차분한 흐름과 섬세함이 돋보이는 인상',
    text: '세로선이 자연스럽게 이어져 얼굴 전체가 차분하고 정돈되어 보여요. 옛 관상식으로는 생각을 천천히 정리하는 섬세한 기운에 빗대곤 해요.',
    keyword: '#차분한인상',
  },
  '균형형': {
    title: '부드러움과 또렷함이 조화로운 인상',
    text: '이마부터 턱까지의 흐름과 좌우 폭이 한쪽으로 치우치지 않고 자연스럽게 이어져요. 전통 관상에서는 이런 조화를 편안한 적응력의 상징으로 풀기도 해요.',
    keyword: '#균형있는인상',
  },
};

function eyeReading(ratio) {
  if (ratio >= 0.205) return '눈의 가로 폭이 얼굴 윤곽 안에서 비교적 또렷하게 보여, 표정의 생동감이 먼저 전해지는 편이에요.';
  if (ratio <= 0.165) return '눈매가 전체 윤곽에 차분하게 어우러져, 처음에는 담백하고 가까이 볼수록 섬세한 분위기가 느껴져요.';
  return '눈매와 얼굴 폭의 비율이 자연스럽게 어우러져, 편안하면서도 또렷한 첫인상을 만들어요.';
}

function mouthReading(ratio) {
  if (ratio >= 0.39) return '입매의 가로선이 비교적 시원하게 보여요. 전통적인 표현으로는 솔직하고 활기찬 소통의 이미지에 빗대곤 해요.';
  if (ratio <= 0.31) return '입매가 단정하게 모여 보여 차분한 분위기를 더해요. 옛 해석에서는 말과 마음을 신중하게 고르는 모습으로 표현하곤 했어요.';
  return '입매가 얼굴 중심과 안정적으로 어우러져 부드럽고 자연스러운 소통의 인상을 더해요.';
}

function harmonyReading(score) {
  if (score >= 0.94) return '사진 속 좌우 흐름도 안정적으로 잡혀 있어 전체적으로 정돈된 인상이 잘 드러났어요.';
  return '표정과 촬영 각도에서 생기는 자연스러운 좌우 차이가 보여, 한층 생동감 있는 분위기가 느껴져요.';
}

export function createFaceReading(measurements, mood = '차분한') {
  const shape = shapeReadings[measurements.faceShape] || shapeReadings['균형형'];
  const safeMood = ['차분한', '밝은', '신비로운', '단단한'].includes(mood) ? mood : '차분한';
  const moodLine = `직접 고른 “${safeMood}”이라는 첫인상 키워드까지 더하면, 본인이 느끼는 이미지와 사진에서 보이는 분위기가 자연스럽게 이어져요.`;
  const result = [
    `사진에서 가장 먼저 보이는 건 ${shape.title.replace(' 인상', '')}이에요.`,
    `얼굴형 · ${shape.text}`,
    `눈매 · ${eyeReading(measurements.eyeRatio)}`,
    `입매 · ${mouthReading(measurements.mouthRatio)}`,
    `전체 조화 · ${harmonyReading(measurements.symmetryScore)} ${moodLine}`,
    '묘미의 한마디 · 지금 가진 인상은 하나로 단정하기보다 표정과 마음에 따라 여러 매력으로 달라질 수 있어요. 편안하게 웃을 때 드러나는 자연스러운 분위기를 가장 좋은 복으로 간직해 보세요.',
    '※ 이 결과는 얼굴 비율을 전통 관상 표현에 연결한 재미용 콘텐츠예요. 외모로 실제 성격·능력·건강·미래를 판단할 수는 없어요.',
  ].join('\n\n');

  return {
    title: shape.title,
    result,
    keywords: [shape.keyword, `#${safeMood}매력`, '#나만의인상'],
    measurements,
  };
}
