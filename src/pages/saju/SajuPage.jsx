import { useState } from 'react';
import SajuChat from './SajuChat.jsx';

export default function SajuPage() {
  const [form, setForm] = useState({ name: '', birth_date: '', birth_time: '', gender: '' });
  const [result, setResult] = useState(null); const [error, setError] = useState(''); const [loading, setLoading] = useState(false);
  function update(event) {
    const { name, value } = event.target;
    let nextValue = value;
    if (name === 'birth_date') {
      const digits = value.replace(/\D/g, '').slice(0, 8);
      const yearText = digits.slice(0, 4);
      const monthText = digits.slice(4, 6);
      const dayText = digits.slice(6, 8);
      const year = yearText.length === 4 ? Math.min(2100, Math.max(1800, Number(yearText))) : null;
      const month = monthText.length === 2 ? Math.min(12, Math.max(1, Number(monthText))) : null;
      const day = dayText.length === 2 ? Math.min(31, Math.max(1, Number(dayText))) : null;
      nextValue = yearText;
      if (monthText) nextValue += `-${month === null ? monthText : month.toString().padStart(2, '0')}`;
      if (dayText) nextValue += `-${day === null ? dayText : day.toString().padStart(2, '0')}`;
      if (year !== null) nextValue = `${year.toString().padStart(4, '0')}${nextValue.slice(4)}`;
    } else if (name === 'birth_time') {
      const match = /^(\d{2}):(\d{2})$/.exec(value);
      if (match) {
        const hour = Math.min(23, Math.max(0, Number(match[1])));
        const minute = Math.min(59, Math.max(0, Number(match[2])));
        nextValue = `${hour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}`;
      }
    }
    setForm((current) => ({ ...current, [name]: nextValue }));
  }
  async function submit(event) {
    event.preventDefault();
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(form.birth_date);
    if (!match) { setError('생년월일을 YYYY-MM-DD 형식으로 입력해 주세요.'); return; }
    const [, yearText, monthText, dayText] = match;
    const year = Number(yearText); const month = Number(monthText); const day = Number(dayText);
    const actualDate = new Date(Date.UTC(year, month - 1, day));
    if (year < 1800 || year > 2100 || actualDate.getUTCFullYear() !== year || actualDate.getUTCMonth() !== month - 1 || actualDate.getUTCDate() !== day) { setError('생년월일은 1800~2100년, 올바른 월·일 범위로 입력해 주세요.'); return; }
    setLoading(true); setError(''); setResult(null);
    try {
      const response = await fetch('/api/saju/readings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: form.name.trim() || null, birth_date: form.birth_date, birth_time: form.birth_time || null, gender: form.gender || null }) });
      const data = await response.json(); if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '생년월일을 1800~2100년 사이로 입력해 주세요.'); setResult(data.reading);
    } catch (caught) { setError(caught.message); } finally { setLoading(false); }
  }
  return <main className="fortune-page"><section className="fortune-intro"><div><span>SAJU</span><h1>사주 풀이</h1><p>생년월일과 출생시간을 입력하면 사주 원국을 확인할 수 있습니다.</p></div></section><section className="fortune-workspace"><form className="fortune-form" onSubmit={submit}><label>이름<input name="name" value={form.name} onChange={update} placeholder="이름" /></label><label>생년월일<input name="birth_date" type="text" inputMode="numeric" placeholder="YYYY-MM-DD" maxLength="10" required value={form.birth_date} onChange={update} /></label><label>출생시간<input name="birth_time" type="time" value={form.birth_time} onChange={update} /></label><label>성별<select name="gender" value={form.gender} onChange={update}><option value="">선택 안 함</option><option value="M">남성</option><option value="F">여성</option></select></label><button className="fortune-submit" disabled={loading}>{loading ? '계산 중...' : '사주 결과 보기'}</button></form>{error && <p role="alert">{error}</p>}{result && <><article className="fortune-result"><h2>사주 계산 결과</h2><p><strong>사주 원국:</strong> {result.pillars}</p><p><strong>격국:</strong> {result.jeonggyeok}</p><p><strong>용신:</strong> {result.yongsin}</p><p><strong>신살:</strong> {result.sinsal?.join(', ') || '없음'}</p></article><SajuChat result={result} /></>}</section></main>;
}
