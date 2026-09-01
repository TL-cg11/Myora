import { useRef, useState } from 'react';
import { analyzeFaceImage, validateImageFile } from '../services/analyzeFaceImage.js';
import CameraCapture from './CameraCapture.jsx';

export default function FaceReadingInput({ onComplete }) {
  const fileRef = useRef(null);
  const [file, setFile] = useState(null);
  const [mood, setMood] = useState('차분한');
  const [cameraOpen, setCameraOpen] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  function selectFile(nextFile) {
    try {
      validateImageFile(nextFile);
      setFile(nextFile);
      setError('');
    } catch (validationError) {
      setFile(null);
      setError(validationError.message);
    }
  }

  async function submit(event) {
    event.preventDefault();
    if (!file || loading) return;
    setLoading(true);
    setError('');
    try {
      const reading = await analyzeFaceImage(file, mood);
      onComplete({
        ...reading,
        summary: `사진 ${file.name}, 인상 키워드 ${mood}`,
      });
    } catch (analysisError) {
      setError(analysisError.message || '얼굴을 분석하지 못했어요. 다른 사진으로 다시 시도해 주세요.');
    } finally {
      setLoading(false);
    }
  }

  return <form className="fortune-form" onSubmit={submit}>
    <div className="face-upload-wrap">
      <button className="photo-upload" type="button" onClick={() => fileRef.current?.click()}>
        <span>＋</span><b>{file?.name || '정면 사진 선택하기'}</b><small>사진은 기기 안에서만 분석하며 서버에 저장하지 않아요.</small>
      </button>
      <button className="camera-trigger" type="button" onClick={() => setCameraOpen((current) => !current)} aria-expanded={cameraOpen}>
        {cameraOpen ? '카메라 닫기' : '카메라로 촬영'}
      </button>
    </div>
    <input ref={fileRef} className="hidden-input" type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => {
      selectFile(event.target.files?.[0]);
      event.target.value = '';
    }}/>
    <CameraCapture open={cameraOpen} onClose={() => setCameraOpen(false)} onCapture={selectFile}/>
    {error && <p className="face-error" role="alert">{error}</p>}
    <fieldset><legend>나와 가까운 첫인상</legend><div className="mood-options">{['차분한', '밝은', '신비로운', '단단한'].map((item) => <button className={mood === item ? 'selected' : ''} type="button" key={item} onClick={() => setMood(item)}>{item}</button>)}</div></fieldset>
    <button className="fortune-submit" type="submit" disabled={!file || loading}>{loading ? '얼굴의 인상을 살펴보고 있어요…' : '나의 관상 결과 보기 →'}</button>
    <p className="face-privacy-note">얼굴 사진은 브라우저 밖으로 전송되지 않아요. 결과는 재미와 참고용으로만 봐 주세요.</p>
  </form>;
}
