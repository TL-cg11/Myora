import { useEffect, useMemo, useRef, useState } from 'react';
import './fortune-experience.css';

const tarotCards = [
  ['달', '감춰진 마음을 천천히 들여다볼 때예요.'],
  ['별', '바라던 방향으로 작은 희망이 자라고 있어요.'],
  ['태양', '솔직한 선택이 좋은 흐름을 불러와요.'],
  ['세계', '하나의 과정이 완성되고 다음 문이 열려요.'],
  ['힘', '부드러운 끈기가 상황을 바꿀 수 있어요.'],
  ['연인', '관계와 가치 사이에서 진심을 확인해 보세요.'],
];

const configs = {
  saju: {
    title: '사주 운세', kicker: '나의 흐름 알아보기', intro: '태어난 날의 정보를 입력하면 오늘의 흐름을 다정하게 풀어드려요.',
    resultTitle: '차분히 힘을 모으는 날',
    result: '오늘은 빠른 결론보다 차근차근 기반을 다지는 흐름이 좋아요. 오전에는 정리, 오후에는 사람과의 대화에서 뜻밖의 실마리를 만날 수 있어요.',
  },
  tarot: {
    title: '타로', kicker: '마음의 카드 고르기', intro: '질문을 마음속에 떠올리고 끌리는 카드 세 장을 골라보세요.',
    resultTitle: '카드가 전하는 오늘의 이야기',
  },
  face: {
    title: '관상', kicker: '나의 인상 발견하기', intro: '사진과 나를 닮은 인상 키워드를 선택하면 매력 포인트를 알려드려요.',
    resultTitle: '당신에게 보이는 따뜻한 매력',
    result: '편안함 속에 또렷한 중심이 느껴지는 인상이에요. 처음에는 차분해 보이지만 가까워질수록 세심함과 유쾌함이 드러나는 타입으로 읽혀요.',
  },
};

function ChatPanel({ context }) {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: '결과를 함께 보고 있어요. 더 궁금한 점을 편하게 물어보세요!' },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  async function sendMessage(text) {
    const question = text.trim();
    if (!question || loading) return;
    const next = [...messages, { role: 'user', content: question }];
    setMessages(next);
    setInput('');
    setLoading(true);

    try {
      const response = await fetch(import.meta.env.VITE_CHAT_API_URL || '/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ context, messages: next }),
      });
      if (!response.ok) throw new Error('AI 응답 서버에 연결할 수 없어요.');
      const data = await response.json();
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

  const suggestions = ['연애운을 더 자세히 알려줘', '오늘 조심할 점은?', '실천하면 좋은 행동은?'];

  return <section className="result-chat" aria-label="운세 결과 AI 채팅">
    <div className="chat-heading"><span className="chat-avatar">✦</span><div><b>묘미에게 더 물어보기</b><small>현재 결과를 기억하고 답변해요</small></div><i>AI</i></div>
    <div className="chat-messages" aria-live="polite">
      {messages.map((message, index) => <div key={`${message.role}-${index}`} className={`chat-bubble ${message.role} ${message.error ? 'error' : ''}`}>{message.content}</div>)}
      {loading && <div className="chat-bubble assistant typing"><span/><span/><span/></div>}
    </div>
    <div className="chat-suggestions">{suggestions.map((item) => <button key={item} type="button" onClick={() => sendMessage(item)}>{item}</button>)}</div>
    <form className="chat-form" onSubmit={(event) => { event.preventDefault(); sendMessage(input); }}>
      <input value={input} onChange={(event) => setInput(event.target.value)} placeholder="결과에 관해 궁금한 점을 물어보세요" aria-label="채팅 질문"/>
      <button type="submit" disabled={!input.trim() || loading}>보내기</button>
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

function TarotInput({ onComplete }) {
  const [selected, setSelected] = useState([]);
  return <div><div className="tarot-grid">{tarotCards.map(([name], index) => {
    const active = selected.includes(index);
    return <button type="button" className={active ? 'selected' : ''} key={name} onClick={() => setSelected((current) => active ? current.filter((card) => card !== index) : current.length < 3 ? [...current, index] : current)}><span>✦</span><b>{active ? name : '?'}</b><small>{active ? `${selected.indexOf(index) + 1}번째 카드` : '카드 선택'}</small></button>;
  })}</div><button className="fortune-submit" disabled={selected.length !== 3} onClick={() => onComplete(selected.map((index) => tarotCards[index][0]).join(' · '))}>선택한 카드 해석하기 ({selected.length}/3) →</button></div>;
}

function FaceInput({ onComplete }) {
  const fileRef = useRef(null);
  const [fileName, setFileName] = useState('');
  const [mood, setMood] = useState('차분한');
  return <form className="fortune-form" onSubmit={(event) => { event.preventDefault(); onComplete(`사진 ${fileName}, 인상 키워드 ${mood}`); }}>
    <button className="photo-upload" type="button" onClick={() => fileRef.current?.click()}><span>＋</span><b>{fileName || '정면 사진 선택하기'}</b><small>사진은 결과 생성 용도로만 사용해요.</small></button>
    <input ref={fileRef} className="hidden-input" type="file" accept="image/*" required onChange={(event) => setFileName(event.target.files?.[0]?.name || '')}/>
    <fieldset><legend>나와 가까운 첫인상</legend><div className="mood-options">{['차분한','밝은','신비로운','단단한'].map((item) => <button className={mood === item ? 'selected' : ''} type="button" key={item} onClick={() => setMood(item)}>{item}</button>)}</div></fieldset>
    <button className="fortune-submit" type="submit" disabled={!fileName}>나의 매력 결과 보기 →</button>
  </form>;
}

export default function FortuneExperience({ type, image }) {
  const config = configs[type];
  const [inputSummary, setInputSummary] = useState('');
  const resultText = useMemo(() => type === 'tarot' && inputSummary
    ? inputSummary.split(' · ').map((name) => tarotCards.find(([card]) => card === name)?.[1]).join(' ')
    : config.result, [config.result, inputSummary, type]);
  const context = `${config.title} 결과. 입력/선택: ${inputSummary}. 결과 제목: ${config.resultTitle}. 해석: ${resultText}`;

  useEffect(() => {
    if (!inputSummary || !resultText) return;
    const history = JSON.parse(localStorage.getItem('myohan-fortune-history') || '[]');
    const entry = { id: Date.now(), type, title: config.title, resultTitle: config.resultTitle, result: resultText, date: new Date().toISOString() };
    localStorage.setItem('myohan-fortune-history', JSON.stringify([entry, ...history].slice(0, 12)));
  }, [config.resultTitle, config.title, inputSummary, resultText, type]);

  return <main className="fortune-page">
    <section className="fortune-intro"><div><span>{config.kicker}</span><h1>{config.title}</h1><p>{config.intro}</p></div><img src={image} alt={`${config.title} 고양이 모미`}/></section>
    <section className="fortune-workspace">
      {!inputSummary ? <div className="input-card"><div className="step-label">STEP 1 · 정보 선택</div>{type === 'saju' && <SajuInput onComplete={setInputSummary}/>} {type === 'tarot' && <TarotInput onComplete={setInputSummary}/>} {type === 'face' && <FaceInput onComplete={setInputSummary}/>}</div>
      : <><article className="fortune-result"><div className="step-label">RESULT · 묘미의 해석</div><span className="result-symbol">☾</span><h2>{config.resultTitle}</h2><p>{resultText}</p><div className="result-keywords"><span>#오늘의흐름</span><span>#나를위한조언</span><span>#다정한운세</span></div><button type="button" onClick={() => setInputSummary('')}>다시 알아보기</button></article><ChatPanel context={context}/></>}
    </section>
  </main>;
}
