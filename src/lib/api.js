/** 타로 API 클라이언트와 비회원 식별자 관리. */

const GUEST_KEY_STORAGE = 'myohan-guest-key';

/** crypto.randomUUID 는 보안 컨텍스트(https/localhost)에서만 있다.
 *  사내 IP 에 http 로 접속하면 없으므로 직접 만든다. */
function randomUuid() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  const bytes = new Uint8Array(16);
  globalThis.crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/** 브라우저마다 하나씩 발급해 두고 계속 쓴다. 이 값으로 내 리딩만 조회한다. */
export function getGuestKey() {
  let key = null;
  try {
    key = localStorage.getItem(GUEST_KEY_STORAGE);
  } catch {
    // 시크릿 모드 등에서 저장소가 막혀 있으면 매번 새로 발급된다(기록만 안 남음).
  }
  if (!key) {
    key = randomUuid();
    try {
      localStorage.setItem(GUEST_KEY_STORAGE, key);
    } catch {
      /* 저장 못 해도 이번 세션은 동작한다. */
    }
  }
  return key;
}

async function readError(response) {
  try {
    const body = await response.json();
    if (typeof body.detail === 'string') return body.detail;
    // 422 는 detail 이 배열로 온다.
    if (Array.isArray(body.detail)) return body.detail.map((item) => item.msg).join(' ');
  } catch {
    /* 본문이 JSON 이 아니면 상태 코드로 안내한다. */
  }
  return response.status >= 500
    ? '서버가 잠시 응답하지 않아요. 잠시 뒤 다시 시도해 주세요.'
    : '요청을 처리하지 못했어요.';
}

async function request(basePath, path, { method = 'GET', body } = {}) {
  let response;
  try {
    response = await fetch(`${basePath}${path}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error('네트워크에 연결할 수 없어요. 연결 상태를 확인해 주세요.');
  }
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

const tarotRequest = (path, options) => request('/api/tarot', path, options);
const faceRequest = (path, options) => request('/api/face', path, options);

export const listSpreads = () => tarotRequest('/spreads');

export const createReading = ({ spreadCode, topic, question }) =>
  tarotRequest('/readings', {
    method: 'POST',
    body: {
      spread_code: spreadCode,
      topic,
      question: question?.trim() ? question.trim() : null,
      guest_key: getGuestKey(),
    },
  });

export const getReading = (readingId) =>
  tarotRequest(`/readings/${readingId}?guest_key=${getGuestKey()}`);

export const listReadings = (limit = 12) =>
  tarotRequest(`/readings?guest_key=${getGuestKey()}&limit=${limit}`);

export const sendChatMessage = (readingId, message) =>
  tarotRequest(`/readings/${readingId}/chat?guest_key=${getGuestKey()}`, {
    method: 'POST',
    body: { message },
  });

export const storeFaceReading = ({ mood, result, measurements, detectorVersion }) =>
  faceRequest('/readings', {
    method: 'POST',
    body: {
      guest_key: getGuestKey(),
      mood,
      detector_version: detectorVersion,
      summary_text: result,
      measurements: {
        aspect_ratio: measurements.aspectRatio,
        jaw_ratio: measurements.jawRatio,
        forehead_ratio: measurements.foreheadRatio,
        eye_ratio: measurements.eyeRatio,
        mouth_ratio: measurements.mouthRatio,
        symmetry_score: measurements.symmetryScore,
        coverage: measurements.coverage,
        roll_degrees: measurements.rollDegrees,
        nose_offset: measurements.noseOffset,
      },
    },
  });

export const listFaceReadings = (limit = 12) =>
  faceRequest(`/readings?guest_key=${getGuestKey()}&limit=${limit}`);
