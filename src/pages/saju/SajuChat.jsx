import { useState } from 'react';

const suggestions = ['오늘의 흐름을 설명해줘', '내 사주에서 강점은 뭐야?', '앞으로 어떤 점을 조심할까?'];

function getErrorMessage(detail) {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => typeof item?.msg === 'string' ? item.msg : '')
      .filter(Boolean);
    if (messages.length) return messages.join(' ');
  }
  return 'AI 응답을 받지 못했습니다.';
}

export default function SajuChat({ result }) {
  const [messages, setMessages] = useState([{ role: 'assistant', content: '결과를 함께 보고 있어요. 더 궁금한 점을 편하게 물어보세요!' }]);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const questionCount = messages.filter((message) => message.role === 'user').length;

  async function sendMessage(value) {
    const text = value.trim();
    if (!text || loading || questionCount >= 5) return;
    const next = [...messages, { role: 'user', content: text }];
    setMessages(next); setQuestion(''); setLoading(true);
    try {
      const response = await fetch('/api/saju/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ context: JSON.stringify(result), messages: next }) });
      const data = await response.json();
      if (!response.ok) throw new Error(getErrorMessage(data.detail));
      setMessages((current) => [...current, { role: 'assistant', content: data.answer }]);
    } catch (error) { setMessages((current) => [...current, { role: 'assistant', content: error.message, error: true }]); }
    finally { setLoading(false); }
  }

  return <section className="result-chat" aria-label="사주 결과 AI 채팅">
    <div className="chat-heading"><span className="chat-avatar">✦</span><div><b>묘라에게 더 물어보기</b><small>현재 결과를 기억하고 답변해요</small></div><i>AI</i></div>
    <div className="chat-limit">AI 질문은 최대 5회 가능해요 · 남은 질문 {5 - questionCount}회</div>
    <div className="chat-messages" aria-live="polite">{messages.map((message, index) => <div key={`${message.role}-${index}`} className={`chat-bubble ${message.role} ${message.error ? 'error' : ''}`}>{message.content}</div>)}{loading && <div className="chat-bubble assistant typing"><span/><span/><span/></div>}</div>
    <div className="chat-suggestions">{suggestions.map((item) => <button key={item} type="button" onClick={() => sendMessage(item)} disabled={loading || questionCount >= 5}>{item}</button>)}</div>
    <form className="chat-form" onSubmit={(event) => { event.preventDefault(); sendMessage(question); }}><input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="결과에 관해 궁금한 점을 물어보세요" maxLength={1500} /><button type="submit" disabled={loading || !question.trim() || questionCount >= 5}>보내기</button></form>
    <p className="chat-notice">AI 해석은 재미와 참고용이며 중요한 결정은 스스로 충분히 검토해 주세요.</p>
  </section>;
}
