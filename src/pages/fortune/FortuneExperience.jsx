import { useEffect, useMemo, useState } from 'react';
import FaceReadingInput from '../../features/face-reading/components/FaceReadingInput.jsx';
import './fortune-experience.css';

const configs = {
  saju: {
    title: '사주 운세', kicker: '나의 흐름 알아보기', intro: '태어난 날의 정보를 입력하면 오늘의 흐름을 다정하게 풀어드려요.',
    resultTitle: '차분히 힘을 모으는 날',
    result: '오늘은 빠른 결론보다 차근차근 기반을 다지는 흐름이 좋아요. 오전에는 정리, 오후에는 사람과의 대화에서 뜻밖의 실마리를 만날 수 있어요.',
  },
  face: {
    title: '관상', kicker: '나의 인상 발견하기', intro: '정면 사진 속 얼굴의 균형을 살펴보고 전통 관상식으로 매력 포인트를 풀어드려요.',
    resultTitle: '당신에게 보이는 따뜻한 매력',
    result: '편안함 속에 또렷한 중심이 느껴지는 인상이에요. 처음에는 차분해 보이지만 가까워질수록 세심함과 유쾌함이 드러나는 타입으로 읽혀요.',
  },
};

function ChatPanel({ context, fortuneType }) {
  const isFaceChat = fortuneType === 'face';
  const questionLimit = isFaceChat ? 5 : Number.POSITIVE_INFINITY;
  const [messages, setMessages] = useState([
    { role: 'assistant', content: '결과를 함께 보고 있어요. 더 궁금한 점을 편하게 물어보세요!' },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [questionCount, setQuestionCount] = useState(0);
  const remainingQuestions = Math.max(0, questionLimit - questionCount);
  const limitReached = isFaceChat && remainingQuestions === 0;

  async function sendMessage(text) {
    const question = text.trim();
    if (!question || loading || limitReached) return;
    const next = [...messages, { role: 'user', content: question }];
    setMessages(next);
    setInput('');
    setLoading(true);
    if (isFaceChat) setQuestionCount((current) => current + 1);

    try {
      const chatApiUrl = isFaceChat
        ? (import.meta.env.VITE_FACE_CHAT_API_URL || '/api/face/chat')
        : (import.meta.env.VITE_CHAT_API_URL || '/api/chat');
      const response = await fetch(chatApiUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ context, messages: next }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'AI 응답 서버에 연결할 수 없어요.');
      const answer = data.answer || data.message?.content || data.content;
      if (!answer) throw new Error('응답 형식을 확인해 주세요.');
      setMessages((current) => [...current, { role: 'assistant', content: answer }]);
    } catch (error) {
      setMessages((current) => [...current, {
        role: 'assistant',
        content: `${error.message} 채팅 서버가 연결되면 이 결과를 바탕으로 바로 답변해 드릴게요.`,
        error: true,
      }]);
    } finally {
      setLoading(false);
    }
  }

  const suggestions = isFaceChat
    ? ['얼굴형을 더 설명해줘', '나의 첫인상 포인트는?', '사진을 잘 찍는 방법은?']
    : ['연애운을 더 자세히 알려줘', '오늘 조심할 점은?', '실천하면 좋은 행동은?'];

  return <section className="result-chat" aria-label="운세 결과 AI 채팅">
    <div className="chat-heading"><span className="chat-avatar">✦</span><div><b>묘라에게 더 물어보기</b><small>현재 결과를 기억하고 답변해요</small></div><i>AI</i></div>
    {isFaceChat && <p className={`chat-limit ${limitReached ? 'exhausted' : ''}`} role="status">
      {limitReached ? 'AI 질문 5회를 모두 사용했어요.' : `AI 질문은 최대 5회 가능해요 · 남은 질문 ${remainingQuestions}회`}
    </p>}
    <div className="chat-messages" aria-live="polite">
      {messages.map((message, index) => <div key={`${message.role}-${index}`} className={`chat-bubble ${message.role} ${message.error ? 'error' : ''}`}>{message.content}</div>)}
      {loading && <div className="chat-bubble assistant typing"><span/><span/><span/></div>}
    </div>
    <div className="chat-suggestions">{suggestions.map((item) => <button key={item} type="button" disabled={loading || limitReached} onClick={() => sendMessage(item)}>{item}</button>)}</div>
    <form className="chat-form" onSubmit={(event) => { event.preventDefault(); sendMessage(input); }}>
      <input value={input} disabled={limitReached} onChange={(event) => setInput(event.target.value)} placeholder={limitReached ? '질문 5회를 모두 사용했어요' : '결과에 관해 궁금한 점을 물어보세요'} aria-label="채팅 질문"/>
      <button type="submit" disabled={!input.trim() || loading || limitReached}>보내기</button>
    </form>
    <p className="chat-notice">AI 해석은 재미와 참고용이며 중요한 결정은 스스로 충분히 검토해 주세요.</p>
  </section>;
}

function SajuInput({ onComplete }) {
  return <form className="fortune-form" onSubmit={(event) => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    onComplete(`이름 ${values.name || '사용자'}, 생년월일 ${values.birth}, 출생시간 ${values.time || '모름'}`);
  }}>
    <label>이름<input name="name" placeholder="이름 또는 닉네임"/></label>
    <label>생년월일<input name="birth" type="date" required/></label>
    <label>태어난 시간<input name="time" type="time"/><small>모르면 비워두어도 괜찮아요.</small></label>
    <button className="fortune-submit" type="submit">내 운세 결과 보기 →</button>
  </form>;
}

export default function FortuneExperience({ type, image }) {
  const config = configs[type];
  const [inputSummary, setInputSummary] = useState('');
  const resultText = useMemo(() => {
    if (type === 'face' && typeof inputSummary === 'object') return inputSummary.result;
    return config.result;
  }, [config.result, inputSummary, type]);
  const resultTitle = type === 'face' && typeof inputSummary === 'object' ? inputSummary.title : config.resultTitle;
  const summaryText = typeof inputSummary === 'object' ? inputSummary.summary : inputSummary;
  const resultKeywords = type === 'face' && typeof inputSummary === 'object'
    ? inputSummary.keywords
    : ['#오늘의흐름', '#나를위한조언', '#다정한운세'];
  const context = `${config.title} 결과. 입력/선택: ${summaryText}. 결과 제목: ${resultTitle}. 해석: ${resultText}`;

  useEffect(() => {
    if (!inputSummary || !resultText) return;
    const history = JSON.parse(localStorage.getItem('myohan-fortune-history') || '[]');
    const entry = { id: Date.now(), type, title: config.title, resultTitle, result: resultText, date: new Date().toISOString() };
    localStorage.setItem('myohan-fortune-history', JSON.stringify([entry, ...history].slice(0, 12)));
  }, [config.title, inputSummary, resultText, resultTitle, type]);

  return <main className="fortune-page">
    <section className="fortune-intro"><div><span>{config.kicker}</span><h1>{config.title}</h1><p>{config.intro}</p></div><img src={image} alt={`${config.title} 고양이 묘라`}/></section>
    <section className="fortune-workspace">
      {!inputSummary ? <div className="input-card"><div className="step-label">STEP 1 · 정보 선택</div>{type === 'saju' && <SajuInput onComplete={setInputSummary}/>} {type === 'face' && <FaceReadingInput onComplete={setInputSummary}/>}</div>
      : <><article className="fortune-result"><div className="step-label">RESULT · 묘라의 해석</div><span className="result-symbol">☾</span><h2>{resultTitle}</h2><p>{resultText}</p><div className="result-keywords">{resultKeywords.map((keyword) => <span key={keyword}>{keyword}</span>)}</div><button type="button" onClick={() => setInputSummary('')}>다시 알아보기</button></article><ChatPanel context={context} fortuneType={type}/></>}
    </section>
  </main>;
}
