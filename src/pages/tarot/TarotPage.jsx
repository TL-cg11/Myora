import { useEffect, useRef, useState } from 'react';
import tarotCat from '../../assets/tarot-cat.png';
import { checkQuestion, createReading, listSpreads, sendChatMessage } from '../../lib/api.js';
import { useAiConfig } from '../../lib/useChatLimit.js';
import { hasDirectIdentifier, DIRECT_IDENTIFIER_MESSAGE } from '../../lib/privacy.js';
import { displayMessageContent, useContextualMessages } from '../../lib/useContextualDisplay.js';
import '../fortune/fortune-experience.css';
import './tarot.css';

// app/routers/tarot.py 의 _TOPIC_LABEL 과 같은 순서/문구를 쓴다.
const TOPICS = [
  ['general', '오늘의 흐름'],
  ['love', '연애운'],
  ['career', '직업운'],
  ['money', '금전운'],
  ['health', '건강운'],
];

// 뒷면으로 깔아 두는 장수. 실제로 어떤 카드가 나오는지는 서버가 정하므로
// 이 숫자는 화면에서 고르는 재미를 위한 값일 뿐이다.
const DECK_SIZE = 12;

/** 이미지가 아직 없으므로 CSS 카드면을 기본으로 쓰고,
 *  image_path 의 그림이 실제로 열릴 때만 그림으로 바꾼다. */
function CardFace({ card, orientation }) {
  const [useImage, setUseImage] = useState(Boolean(card.image_path));
  const number = card.code.split('-')[1] ?? '';
  const reversed = orientation === 'reversed';

  return (
    <div className={`tarot-card-face ${reversed ? 'is-reversed' : ''}`}>
      {useImage ? (
        <img src={card.image_path} alt={card.name_ko} onError={() => setUseImage(false)} />
      ) : (
        <div className="card-drawn">
          <span className="card-corner">{number}</span>
          {reversed && <span className="card-reversed-mark">역</span>}
          <span className="card-symbol">✦</span>
          <b>{card.name_ko}</b>
          <small>{card.name_en}</small>
        </div>
      )}
    </div>
  );
}

function SetupStep({ spreads, value, onChange, onSubmit, loading, error }) {
  const { spreadCode, topic, question } = value;

  return (
    <div className="input-card">
      <div className="step-label">STEP 1 · 스프레드와 주제</div>

      <div className="tarot-field">
        <h3>어떻게 볼까요?</h3>
        <div className="spread-options">
          {spreads.map((spread) => (
            <button
              type="button"
              key={spread.code}
              className={spread.code === spreadCode ? 'selected' : ''}
              onClick={() => onChange({ ...value, spreadCode: spread.code })}
            >
              <b>{spread.name_ko}</b>
              <em>{spread.card_count}장</em>
              <small>{spread.description}</small>
            </button>
          ))}
        </div>
      </div>

      <div className="tarot-field">
        <h3>무엇이 궁금한가요?</h3>
        <div className="topic-options">
          {TOPICS.map(([code, label]) => (
            <button
              type="button"
              key={code}
              className={code === topic ? 'selected' : ''}
              onClick={() => onChange({ ...value, topic: code })}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="tarot-field">
        <h3>질문을 적어 두면 결과와 함께 남아요 <small>(선택)</small></h3>
        <input
          value={question}
          maxLength={255}
          placeholder="예) 지금 이 일을 계속 해도 될까요?"
          onChange={(event) => onChange({ ...value, question: event.target.value })}
        />
      </div>

      {error && <p className="tarot-error">{error}</p>}
      <button className="fortune-submit" type="button" disabled={!spreadCode || loading} onClick={onSubmit}>
        카드 뽑으러 가기 →
      </button>
    </div>
  );
}

function PickStep({ spread, picked, onPick, onSubmit, loading, error }) {
  const need = spread.card_count;
  const done = picked.length === need;

  return (
    <div className="input-card">
      <div className="step-label">STEP 2 · 카드 고르기</div>
      <h3 className="pick-title">마음에 드는 카드를 {need}장 골라주세요</h3>
      <p className="pick-guide">
        질문을 떠올리며 천천히 고르면 돼요. 자리 순서는 고른 순서대로{' '}
        {spread.positions.map((position) => position.label_ko).join(' · ')} 예요.
      </p>

      <div className="tarot-deck">
        {Array.from({ length: DECK_SIZE }, (_, index) => {
          const order = picked.indexOf(index);
          const selected = order !== -1;
          return (
            <button
              type="button"
              key={index}
              className={`card-back ${selected ? 'selected' : ''} ${!selected && done ? 'locked' : ''}`}
              disabled={loading}
              aria-pressed={selected}
              aria-label={selected ? `${order + 1}번째로 고른 카드` : `${index + 1}번 카드 고르기`}
              onClick={() => onPick(index)}
            >
              <span className="card-back-art">✦</span>
              {selected && <em>{spread.positions[order]?.label_ko ?? order + 1}</em>}
            </button>
          );
        })}
      </div>

      {error && <p className="tarot-error">{error}</p>}
      <button className="fortune-submit" type="button" disabled={!done || loading} onClick={onSubmit}>
        {loading ? '카드를 펼치는 중…' : `선택한 카드 해석하기 (${picked.length}/${need}) →`}
      </button>
    </div>
  );
}


function ChatPanel({ reading }) {
  // 리딩을 만들 때 서버가 넣어둔 첫 인사가 messages 에 이미 있다. 이 인사말에
  // policy_version을 채우기 전(과거)에 만들어진 리딩은 서버가 그 메시지를
  // 걸러내므로 messages가 비어 있을 수 있다 — 그 경우에만 이 기본값을 쓴다.
  const [messages, setMessages] = useContextualMessages(reading.messages ?? [
    { seq: 1, role: 'assistant', content: '결과를 함께 보고 있어요. 더 궁금한 점을 편하게 물어보세요!' },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [source, setSource] = useState(null);
  const listRef = useRef(null);

  // 관상(FortuneExperience)은 별도 카운터를 두지만, 타로는 대화가 서버에 저장되고
  // 응답으로 전체가 돌아오므로 실제 메시지에서 센다. 새로고침해도 값이 어긋나지 않는다.
  const { chatQuestionLimit: questionLimit, messageMaxChars } = useAiConfig();
  const usedQuestions = messages.filter((message) => message.role === 'user').length;
  const remainingQuestions = Math.max(0, questionLimit - usedQuestions);
  const limitReached = remainingQuestions === 0;

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, loading]);

  async function send(text) {
    const question = text.trim();
    if (!question || loading || limitReached) return;
    setMessages((current) => [...current, { seq: `local-${current.length}`, role: 'user', content: question }]);
    setInput('');
    setLoading(true);
    try {
      const result = await sendChatMessage(reading.id, question);
      // 서버가 돌려준 전체 대화로 맞춰 두면 낙관적으로 넣은 말풍선과 어긋나지 않는다.
      // 구버전 서버의 대체 문구가 돌아오더라도 방금 입력한 원문은 유지한다.
      // 현재 서버는 안전 판정과 관계없이 질문 원문을 저장한다.
      const lastUserIndex = result.messages.reduce(
        (found, message, index) => (message.role === 'user' ? index : found), -1,
      );
      setMessages(
        lastUserIndex === -1
          ? result.messages
          : result.messages.map((message, index) =>
              index === lastUserIndex ? { ...message, content: question } : message,
            ),
      );
      setSource(result.source);
    } catch (cause) {
      setMessages((current) => [...current, { seq: `error-${current.length}`, role: 'assistant', content: cause.message, error: true }]);
    } finally {
      setLoading(false);
    }
  }

  const suggestions = ['이 카드가 왜 나왔을까?', '지금 조심할 점은?', '실천하면 좋은 행동은?'];

  return (
    <section className="result-chat" aria-label="타로 결과 채팅">
      <div className="chat-heading">
        <span className="chat-avatar">✦</span>
        <div><b>묘라에게 더 물어보기</b><small>뽑은 카드를 기억하고 답변해요</small></div>
        <i>{source === 'llm' ? 'AI' : source === 'rule' ? '카드 기반' : 'AI'}</i>
      </div>
      <p className={`chat-limit ${limitReached ? 'exhausted' : ''}`} role="status">
        {limitReached
          ? `AI 질문 ${questionLimit}회를 모두 사용했어요.`
          : `AI 질문은 최대 ${questionLimit}회 가능해요 · 남은 질문 ${remainingQuestions}회`}
      </p>
      <div className="chat-messages" ref={listRef} aria-live="polite">
        {messages.map((message) => (
          <div key={message.seq} className={`chat-bubble ${message.role} ${message.error ? 'error' : ''}`}>
            {displayMessageContent(message)}
          </div>
        ))}
        {loading && <div className="chat-bubble assistant typing"><span/><span/><span/></div>}
      </div>
      <div className="chat-suggestions">
        {suggestions.map((item) => (
          <button key={item} type="button" disabled={loading || limitReached} onClick={() => send(item)}>{item}</button>
        ))}
      </div>
      <form className="chat-form" onSubmit={(event) => { event.preventDefault(); send(input); }}>
        <input value={input} maxLength={messageMaxChars} disabled={limitReached}
               onChange={(event) => setInput(event.target.value)}
               placeholder={limitReached ? `질문 ${questionLimit}회를 모두 사용했어요` : '결과에 관해 궁금한 점을 물어보세요'}
               aria-label="채팅 질문"/>
        <button type="submit" disabled={!input.trim() || loading || limitReached}>보내기</button>
      </form>
      <p className="chat-notice">타로 해석은 재미와 참고용이며 중요한 결정은 스스로 충분히 검토해 주세요.</p>
    </section>
  );
}

function ResultStep({ reading, onRestart }) {
  const topicLabel = TOPICS.find(([code]) => code === reading.topic)?.[1] ?? '오늘의 흐름';

  return (
    <>
      <article className="fortune-result tarot-result">
        <div className="step-label">RESULT · 묘라의 해석</div>
        <span className="result-symbol">☾</span>
        <h2>{reading.summary_title}</h2>
        <p className="result-meta">
          {reading.spread.name_ko} · {topicLabel}
          {reading.question && <em>“{reading.question}”</em>}
        </p>

        <div className="reading-cards">
          {reading.cards.map((entry) => (
            <section className="reading-card" key={entry.position_no}>
              <CardFace card={entry.card} orientation={entry.orientation} />
              <div className="reading-card-body">
                <span className="position-label">
                  {entry.label_ko}
                  <i>{entry.orientation === 'reversed' ? '역방향' : '정방향'}</i>
                </span>
                <h3>{entry.card.name_ko}</h3>
                {entry.position_description && <small>{entry.position_description}</small>}
                <div className="result-keywords">
                  {entry.keywords.map((keyword) => (
                    <span key={keyword}>#{keyword}</span>
                  ))}
                </div>
                <p>{entry.meaning}</p>
              </div>
            </section>
          ))}
        </div>

        <button type="button" onClick={onRestart}>다시 뽑기</button>
      </article>
      <ChatPanel reading={reading} />
    </>
  );
}

export default function TarotPage() {
  const [spreads, setSpreads] = useState([]);
  const [setup, setSetup] = useState({ spreadCode: '', topic: 'general', question: '' });
  const [step, setStep] = useState('setup');
  const [picked, setPicked] = useState([]);
  const [reading, setReading] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    listSpreads()
      .then((items) => {
        if (!alive) return;
        setSpreads(items);
        setSetup((current) => ({ ...current, spreadCode: current.spreadCode || items[0]?.code || '' }));
      })
      .catch((cause) => alive && setError(cause.message))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  const spread = spreads.find((item) => item.code === setup.spreadCode);

  function togglePick(index) {
    setPicked((current) => {
      if (current.includes(index)) return current.filter((item) => item !== index);
      if (current.length >= (spread?.card_count ?? 0)) return current;
      return [...current, index];
    });
  }

  /** 질문은 STEP 1에서 적고 서버 요청은 STEP 2에서 나간다. 여기서 먼저 걸러야
   *  사용자가 입력창이 있는 화면에서 바로 고칠 수 있다. 최종 판정은 서버가 한다. */
  async function goToPick() {
    const question = setup.question?.trim() ?? '';
    if (hasDirectIdentifier(question)) {
      setError(DIRECT_IDENTIFIER_MESSAGE);
      return;
    }
    if (question) {
      setLoading(true);
      try {
        await checkQuestion(question);
      } catch (cause) {
        setError(cause.message);
        return;
      } finally {
        setLoading(false);
      }
    }
    setPicked([]);
    setError('');
    setStep('pick');
  }

  async function submitReading() {
    setLoading(true);
    setError('');
    try {
      // 뽑기는 서버가 한다. 화면에서 고른 순서는 자리 순서를 정하는 연출일 뿐이다.
      setReading(await createReading(setup));
      setStep('result');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (cause) {
      setError(cause.message);
      // 최초 질문이 반려되면 카드 고르기 화면에는 고칠 입력창이 없다. 입력 화면으로 되돌린다.
      if (cause.status === 400) setStep('setup');
    } finally {
      setLoading(false);
    }
  }

  function restart() {
    setReading(null);
    setPicked([]);
    setStep('setup');
    setError('');
  }

  return (
    <main className="fortune-page">
      <section className="fortune-intro">
        <div>
          <span>마음의 카드 고르기</span>
          <h1>타로</h1>
          <p>질문을 마음속에 떠올리고 끌리는 카드를 골라보세요.</p>
        </div>
        <img src={tarotCat} alt="타로 고양이 묘라" />
      </section>

      <section className="fortune-workspace">
        {step === 'setup' && (
          loading && spreads.length === 0
            ? <div className="input-card tarot-loading">카드를 준비하고 있어요…</div>
            : spreads.length === 0
              ? <div className="input-card tarot-loading">{error || '지금은 카드를 준비할 수 없어요.'}</div>
              : <SetupStep
                  spreads={spreads}
                  value={setup}
                  onChange={(next) => { setSetup(next); if (error) setError(''); }}
                  loading={loading}
                  error={error}
                  onSubmit={goToPick}
                />
        )}

        {step === 'pick' && spread && (
          <PickStep
            spread={spread}
            picked={picked}
            onPick={togglePick}
            onSubmit={submitReading}
            loading={loading}
            error={error}
          />
        )}

        {step === 'result' && reading && <ResultStep reading={reading} onRestart={restart} />}
      </section>
    </main>
  );
}
