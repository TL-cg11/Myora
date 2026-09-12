import { useEffect, useState } from 'react';
import { getAuthToken } from './api.js';

// 서버가 응답하기 전이나 조회에 실패했을 때 쓸 값. app/config.py 의 기본값과 같다.
const FALLBACK_CONFIG = {
  chatQuestionLimit: 5,
  messageMaxChars: 1500,
};

let cached = null;
let inFlight = null;
const subscribers = new Set();

function loadConfig() {
  inFlight ??= fetch('/api/config', {
    // 로그인 상태에 따라 값이 달라진다(관리자 계정은 질문 한도가 늘어난다).
    headers: getAuthToken() ? { Authorization: `Bearer ${getAuthToken()}` } : {},
  })
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
  return inFlight;
}

/** 로그인·로그아웃으로 계정이 바뀌면 캐시를 버리고 다시 받아, 열려 있는 화면에도
 *  알려 준다. 그러지 않으면 새로고침 전까지 관리자 로그인 후에도 예전 한도가
 *  화면에 남는다(실제 요청 처리는 서버가 다시 계산하므로 안전에는 영향이 없다).
 */
function refreshConfig() {
  cached = null;
  loadConfig().then((value) => subscribers.forEach((setConfig) => setConfig(value)));
}

if (typeof globalThis.addEventListener === 'function') {
  globalThis.addEventListener('myohan-auth-changed', refreshConfig);
}

/** 채팅 질문 한도를 서버에서 받아 온다.
 *
 *  숫자를 화면에 하드코딩하면 서버(config.py)만 바꿨을 때 안내 문구와 실제
 *  동작이 어긋난다. 세 기능(사주·관상·타로)이 같은 값을 쓰므로 모듈 수준에
 *  캐시해 페이지를 옮겨 다녀도 요청은 한 번만 나간다.
 */
export function useAiConfig() {
  const [config, setConfig] = useState(cached ?? FALLBACK_CONFIG);

  useEffect(() => {
    subscribers.add(setConfig);
    if (cached === null) {
      loadConfig().then((value) => { if (subscribers.has(setConfig)) setConfig(value); });
    }
    return () => { subscribers.delete(setConfig); };
  }, []);

  return config;
}

export function useChatLimit() {
  return useAiConfig().chatQuestionLimit;
}
