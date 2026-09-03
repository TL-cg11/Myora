import { useEffect, useRef, useState } from 'react';
import { getCameraSupport, requestUserCamera } from '../services/cameraAccess.js';

function cameraErrorMessage(error) {
  if (error?.name === 'NotAllowedError') return '카메라 권한이 꺼져 있어요. 브라우저 설정에서 카메라를 허용해 주세요.';
  if (error?.name === 'NotFoundError') return '연결된 카메라를 찾지 못했어요.';
  if (error?.name === 'NotReadableError') return '다른 앱에서 카메라를 사용 중인지 확인해 주세요.';
  return '카메라를 시작하지 못했어요. HTTPS 또는 localhost에서 접속했는지 확인해 주세요.';
}

export default function CameraCapture({ open, onCapture, onClose, onFallbackCapture }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [error, setError] = useState('');
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!open) return undefined;
    let cancelled = false;
    setError('');
    setReady(false);

    async function startCamera() {
      const support = getCameraSupport();
      if (!support.supported) {
        setError(support.message);
        return;
      }
      try {
        const stream = await requestUserCamera({
          audio: false,
          video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 1280 } },
        });
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
          setReady(true);
        }
      } catch (cameraError) {
        setError(cameraErrorMessage(cameraError));
      }
    }

    startCamera();
    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    };
  }, [open]);

  function capture() {
    const video = videoRef.current;
    if (!video?.videoWidth || !video?.videoHeight) return;
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext('2d');
    context.translate(canvas.width, 0);
    context.scale(-1, 1);
    context.drawImage(video, 0, 0);
    canvas.toBlob((blob) => {
      if (!blob) {
        setError('사진을 저장하지 못했어요. 다시 촬영해 주세요.');
        return;
      }
      onCapture(new File([blob], `camera-${Date.now()}.jpg`, { type: 'image/jpeg' }));
      onClose();
    }, 'image/jpeg', 0.92);
  }

  if (!open) return null;
  return <div className="camera-panel" aria-label="카메라 촬영 테스트">
    <div className="camera-preview">
      <video ref={videoRef} playsInline muted aria-label="카메라 미리보기"/>
      {!ready && !error && <span>카메라를 준비하고 있어요…</span>}
    </div>
    {error && <p className="face-error" role="alert">{error}</p>}
    <div className="camera-actions">
      <button type="button" onClick={onClose}>닫기</button>
      {ready
        ? <button type="button" onClick={capture}>이 화면 촬영하기</button>
        : <button type="button" onClick={onFallbackCapture}>기기 카메라 열기</button>}
    </div>
    <small>정면을 보고 얼굴 전체가 화면 안에 들어오게 해 주세요.</small>
  </div>;
}
