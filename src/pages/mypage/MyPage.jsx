import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { listFaceReadings, listReadings as listTarotReadings } from '../../lib/api.js';
import './mypage.css';

const typeMeta = {
  saju: { icon: '☯', path: '/saju', color: 'lilac' },
  tarot: { icon: '✦', path: '/tarot', color: 'pink' },
  face: { icon: '☾', path: '/face', color: 'blue' },
};

// app/routers/tarot.py 의 _TOPIC_LABEL 과 같은 문구.
const TOPIC_LABEL = {
  general: '오늘의 흐름', love: '연애운', career: '직업운', money: '금전운', health: '건강운',
};

function readLocalHistory() {
  try {
    return JSON.parse(localStorage.getItem('myohan-fortune-history') || '[]');
  } catch {
    return [];   // 저장소가 막혔거나 값이 깨졌으면 없는 것으로 본다.
  }
}

/** 서버 리딩을 로컬 기록과 같은 모양으로 맞춘다. 사주·관상이 서버로 오면
 *  이 함수만 남기고 로컬 쪽을 지우면 된다. */
function fromServer(reading) {
  return {
    id: `tarot-${reading.id}`,          // 로컬 기록의 Date.now() id 와 겹치지 않게
    type: 'tarot',
    title: `${reading.spread_name} · ${TOPIC_LABEL[reading.topic] ?? '오늘의 흐름'}`,
    resultTitle: reading.summary_title,
    result: reading.card_names.join(' · '),
    date: reading.created_at,
    stored: 'server',
  };
}

function fromFaceServer(reading) {
  return {
    id: `face-${reading.id}`,
    type: 'face',
    title: `관상 · ${reading.mood || '첫인상'}`,
    resultTitle: reading.summary_title,
    result: reading.summary_text,
    date: reading.created_at,
    stored: 'server',
  };
}

export default function MyPage() {
  const [name, setName] = useState(() => localStorage.getItem('myohan-profile-name') || '묘한 손님');
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(name);
  const [local, setLocal] = useState(readLocalHistory);
  const [server, setServer] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    Promise.allSettled([listTarotReadings(), listFaceReadings()])
      .then(([tarotResult, faceResult]) => {
        if (!alive) return;
        const tarot = tarotResult.status === 'fulfilled' ? tarotResult.value.map(fromServer) : [];
        const face = faceResult.status === 'fulfilled' ? faceResult.value.map(fromFaceServer) : [];
        setServer([...tarot, ...face]);
        const failures = [tarotResult, faceResult]
          .filter((result) => result.status === 'rejected')
          .map((result) => result.reason?.message)
          .filter(Boolean);
        setError(failures.join(' '));
      })
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, []);

  const history = [...server, ...local].sort((a, b) => new Date(b.date) - new Date(a.date));

  function saveName(event) {
    event.preventDefault();
    const nextName = draft.trim() || '묘한 손님';
    setName(nextName);
    localStorage.setItem('myohan-profile-name', nextName);
    setEditing(false);
  }

  // 서버 기록을 지우는 API 가 아직 없다. 이 버튼은 이 브라우저에 남은 것만 지운다.
  function clearLocal() {
    localStorage.removeItem('myohan-fortune-history');
    setLocal([]);
  }

  return <main className="mypage">
    <section className="mypage-hero">
      <div className="profile-avatar">ฅ</div>
      <div className="profile-copy"><span>MY PAGE</span>{editing
        ? <form onSubmit={saveName}><input autoFocus value={draft} onChange={(event) => setDraft(event.target.value)} maxLength="16"/><button type="submit">저장</button><button type="button" onClick={() => setEditing(false)}>취소</button></form>
        : <h1>{name}님, 반가워요 <button type="button" onClick={() => { setDraft(name); setEditing(true); }}>수정</button></h1>}
        <p>내가 만난 운세와 묘라의 이야기를 한곳에서 확인하세요.</p>
      </div>
      <div className="profile-stats"><div><b>{history.length}</b><span>본 운세</span></div><div><b>{new Set(history.map((item) => item.type)).size}</b><span>이용 서비스</span></div></div>
    </section>

    <section className="mypage-layout">
      <div className="mypage-main">
        <div className="mypage-title">
          <div><span>RECENT FORTUNE</span><h2>최근 본 운세</h2></div>
          {local.length > 0 && <button type="button" onClick={clearLocal}>이 기기 기록 지우기</button>}
        </div>

        {loading
          ? <div className="empty-history"><span>☾</span><h3>기록을 불러오는 중이에요</h3></div>
          : history.length > 0
            ? <><div className="history-list">{history.map((item) => {
                const meta = typeMeta[item.type] || typeMeta.saju;
                return <article className="history-card" key={item.id}>
                  <div className={`history-icon ${meta.color}`}>{meta.icon}</div>
                  <div>
                    <span>{item.title} · {new Date(item.date).toLocaleDateString('ko-KR')}</span>
                    <h3>{item.resultTitle}</h3>
                    <p>{item.result}</p>
                  </div>
                  <Link to={meta.path}>다시 보기 →</Link>
                </article>;
              })}</div>
              {error && <p className="history-notice warn">일부 서버 기록을 불러오지 못했어요. {error}</p>}
              </>
            : <div className="empty-history"><span>☾</span><h3>아직 만난 운세가 없어요</h3><p>{error || '오늘의 마음과 가장 가까운 방법으로 첫 이야기를 만나보세요.'}</p><Link to="/tarot">운세 보러 가기 →</Link></div>}
      </div>

      <aside className="mypage-side">
        <section><span>QUICK MENU</span><h2>새로운 운세 보기</h2><nav><Link to="/saju"><b>☯</b><div>사주 운세<small>오늘의 흐름 살펴보기</small></div><i>›</i></Link><Link to="/tarot"><b>✦</b><div>타로<small>마음의 카드 고르기</small></div><i>›</i></Link><Link to="/face"><b>☾</b><div>관상<small>나의 인상 발견하기</small></div><i>›</i></Link></nav></section>
        <section className="mypage-settings"><span>SETTINGS</span><h2>이용 설정</h2><label><div>운세 알림<small>오늘의 한마디를 알려드려요</small></div><input type="checkbox"/><i/></label><label><div>채팅 기록 저장<small>이 기기에 대화를 보관해요</small></div><input type="checkbox" defaultChecked/><i/></label>
          <p>타로와 관상 기록은 서버에 저장되지만, 그 기록을 여는 열쇠는 이 브라우저에만 있어요. 브라우저 데이터를 지우거나 다른 기기에서 접속하면 이전 기록을 찾을 수 없어요.</p>
        </section>
      </aside>
    </section>
  </main>;
}
