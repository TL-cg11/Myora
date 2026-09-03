import { useEffect, useState } from 'react';
import tarotCat from '../../assets/tarot-cat.png';
import { createReading, listSpreads } from '../../lib/api.js';
import '../fortune/fortune-experience.css';
import './tarot.css';

// app/services/tarot.py 의 _TOPIC_LABEL 과 같은 순서/문구를 쓴다.
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

function ResultStep({ reading, onRestart }) {
  const topicLabel = TOPICS.find(([code]) => code === reading.topic)?.[1] ?? '오늘의 흐름';

  return (
    <>
      <article className="fortune-result tarot-result">
        <div className="step-label">RESULT · 묘미의 해석</div>
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
        <img src={tarotCat} alt="타로 고양이 모미" />
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
                  onChange={setSetup}
                  loading={loading}
                  error={error}
                  onSubmit={() => { setPicked([]); setError(''); setStep('pick'); }}
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
