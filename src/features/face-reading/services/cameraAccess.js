const LOCAL_CAMERA_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]']);

function legacyGetUserMedia() {
  return navigator.getUserMedia
    || navigator.webkitGetUserMedia
    || navigator.mozGetUserMedia;
}

export function getCameraSupport() {
  const isLocalhost = LOCAL_CAMERA_HOSTS.has(window.location.hostname);
  const isSecure = window.isSecureContext || isLocalhost;
  const hasModernApi = Boolean(navigator.mediaDevices?.getUserMedia);
  const hasLegacyApi = Boolean(legacyGetUserMedia());
  const localTestUrl = `http://localhost${window.location.port ? `:${window.location.port}` : ''}/face`;

  if (!isSecure) {
    return {
      supported: false,
      reason: 'insecure',
      message: `현재 접속 주소는 카메라가 차단되는 HTTP 환경이에요. 이 컴퓨터에서는 ${localTestUrl}로 접속하고, 다른 기기에서는 HTTPS 주소를 사용해 주세요.`,
    };
  }
  if (!hasModernApi && !hasLegacyApi) {
    return {
      supported: false,
      reason: 'unsupported',
      message: '현재 브라우저가 실시간 카메라를 제공하지 않아요. 아래 “기기 카메라 열기”를 누르거나 Chrome·Edge·Safari에서 열어 주세요.',
    };
  }
  return { supported: true, reason: null, message: '' };
}

export async function requestUserCamera(constraints) {
  if (navigator.mediaDevices?.getUserMedia) {
    return navigator.mediaDevices.getUserMedia(constraints);
  }
  const legacyApi = legacyGetUserMedia();
  if (!legacyApi) throw new DOMException('Camera API is unavailable', 'NotSupportedError');
  return new Promise((resolve, reject) => {
    legacyApi.call(navigator, constraints, resolve, reject);
  });
}
