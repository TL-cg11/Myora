import { useEffect, useState } from 'react';

// 서버가 응답하기 전이나 조회에 실패했을 때 쓸 값. app/config.py 의 기본값과 같다.
const FALLBACK_CONFIG = {
  chatQuestionLimit: 5,
  messageMaxChars: 1500,
};

let cached = null;
let inFlight = null;

/** 채팅 질문 한도를 서버에서 한 번만 받아 온다.
 *
 *  숫자를 화면에 하드코딩하면 서버(config.py)만 바꿨을 때 안내 문구와 실제
 *  동작이 어긋난다. 세 기능(사주·관상·타로)이 같은 값을 쓰므로 모듈 수준에
 *  캐시해 페이지를 옮겨 다녀도 요청은 한 번만 나간다.
 */
export function useAiConfig() {
  const [config, setConfig] = useState(cached ?? FALLBACK_CONFIG);

  useEffect(() => {
    if (cached !== null) return;
    let alive = true;
    inFlight ??= fetch('/api/config')
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        const questionLimit = Number(data?.chat_question_limit);
        const messageMaxChars = Number(data?.ai_message_max_chars);
        cached = {
          chatQuestionLimit: Number.isFinite(questionLimit) && questionLimit > 0
            ? questionLimit : FALLBACK_CONFIG.chatQuestionLimit,
          messageMaxChars: Number.isFinite(messageMaxChars) && messageMaxChars > 0
            ? messageMaxChars : FALLBACK_CONFIG.messageMaxChars,
        };
        return cached;
      })
      .catch(() => {
        // 못 받아도 화면은 떠야 한다. 서버가 실제 기준이라 한도는 어차피 지켜진다.
        cached = FALLBACK_CONFIG;
        return cached;
      })
      .finally(() => { inFlight = null; });

    inFlight.then((value) => { if (alive) setConfig(value); });
    return () => { alive = false; };
  }, []);

  return config;
}

export function useChatLimit() {
  return useAiConfig().chatQuestionLimit;
}
