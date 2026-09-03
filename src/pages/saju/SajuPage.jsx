import { useState } from 'react';

export default function SajuPage() {
  const [form, setForm] = useState({ name: '', birth_date: '', birth_time: '', gender: '' });
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  function update(event) {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
  }

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const response = await fetch('/api/saju/readings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, birth_time: form.birth_time || null, gender: form.gender || null }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || '사주 결과를 불러오지 못했습니다.');
      setResult(data.reading);
    } catch (caught) {
      setError(caught.message);
    } finally {
      setLoading(false);
    }
  }

  return <main className="fortune-page">
    <section className="fortune-intro"><div><span>SAJU</span><h1>사주 풀이</h1><p>생년월일과 출생시간을 입력하면 사주 원국을 확인할 수 있습니다.</p></div></section>
    <section className="fortune-workspace">
      <form className="fortune-form" onSubmit={submit}>
        <label>이름<input name="name" value={form.name} onChange={update} placeholder="이름" /></label>
        <label>생년월일<input name="birth_date" type="date" required value={form.birth_date} onChange={update} /></label>
        <label>출생시간<input name="birth_time" type="time" value={form.birth_time} onChange={update} /></label>
        <label>성별<select name="gender" value={form.gender} onChange={update}><option value="">선택 안 함</option><option value="M">남성</option><option value="F">여성</option></select></label>
        <button className="fortune-submit" disabled={loading}>{loading ? '계산 중...' : '사주 결과 보기'}</button>
      </form>
      {error && <p role="alert">{error}</p>}
      {result && <article className="fortune-result"><h2>사주 계산 결과</h2><p><strong>사주 원국:</strong> {result.pillars}</p><p><strong>격국:</strong> {result.jeonggyeok}</p><p><strong>용신:</strong> {result.yongsin}</p><p><strong>신살:</strong> {result.sinsal?.join(', ') || '없음'}</p></article>}
    </section>
  </main>;
}
