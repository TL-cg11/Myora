import { useState } from 'react';
import SajuChat from './SajuChat.jsx';
import { getGuestKey } from '../../lib/api.js';
import SajuMeaning from './SajuMeaning.jsx';

export default function SajuPage() {
  const [form, setForm] = useState({ name: '', birth_date: '', birth_time: '', gender: '' });
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  function update(event) {
    const { name, value } = event.target;
    if (name === 'birth_date' && /^\d{4}/.test(value)) {
      const year = Number(value.slice(0, 4));
      if (year < 1900 || year > 2100) {
        setError('생년월일은 1900~2100년 사이로 입력해 주세요.');
        return;
      }
    }
    setForm((current) => ({ ...current, [name]: value }));
  }

  async function submit(event) {
    event.preventDefault();
    const birthYear = Number(form.birth_date.slice(0, 4));
    if (!/^\d{4}-\d{2}-\d{2}$/.test(form.birth_date) || birthYear < 1900 || birthYear > 2100) {
      setError('생년월일은 1900~2100년 사이로 입력해 주세요.');
      return;
    }
    setLoading(true); setError(''); setResult(null);
    try {
      const response = await fetch('/api/saju/readings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: form.name.trim() || null,
          birth_date: form.birth_date,
          birth_time: form.birth_time || null,
          gender: form.gender || null,
          guest_key: getGuestKey(),
        }),
      });
      const body = await response.text();
      let data;
      try {
        data = body ? JSON.parse(body) : {};
      } catch {
        throw new Error(`서버 오류 (${response.status})`);
      }
      if (!response.ok) {
        const detail = typeof data.detail === 'string'
          ? data.detail
          : Array.isArray(data.detail) ? data.detail.map((item) => item.msg).join(' ') : `서버 오류 (${response.status})`;
        throw new Error(detail);
      }
      setResult(data.reading);
    } catch (caught) {
      setError(caught.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="fortune-page">
      <section className="fortune-intro"><div><span>SAJU</span><h1>사주 상담</h1><p>생년월일과 출생시간을 입력하면 사주 결과를 확인할 수 있습니다.</p></div></section>
      <section className="fortune-workspace">
        <form className="fortune-form" onSubmit={submit}>
          <label>이름<input name="name" value={form.name} onChange={update} placeholder="이름" /></label>
          <label>생년월일<input name="birth_date" type="date" min="1900-01-01" max="2100-12-31" required value={form.birth_date} onChange={update} /></label>
          <label>출생시간<input name="birth_time" type="time" value={form.birth_time} onChange={update} /></label>
          <label>성별<select name="gender" value={form.gender} onChange={update}><option value="">선택 안 함</option><option value="M">남성</option><option value="F">여성</option></select></label>
          <button className="fortune-submit" disabled={loading}>{loading ? '계산 중...' : '사주 결과 보기'}</button>
        </form>
        {error && <p role="alert">{error}</p>}
        {result && <><article className="fortune-result"><h2>사주 계산 결과</h2>
          {result.interpretation ? <SajuMeaning interpretation={result.interpretation} /> : <>
            <p><strong>사주 원국:</strong> {result.pillars}</p><p><strong>정격:</strong> {result.jeonggyeok}</p>
            <p><strong>용신:</strong> {result.yongsin}</p><p><strong>신살:</strong> {result.sinsal?.join(', ') || '없음'}</p>
          </>}
        </article><SajuChat result={result} /></>}
      </section>
    </main>
  );
}
