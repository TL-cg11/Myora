import { useState } from 'react';
import { Link } from 'react-router-dom';
import './mypage.css';

const typeMeta = {
  saju: { icon: '☯', path: '/saju', color: 'lilac' },
  tarot: { icon: '✦', path: '/tarot', color: 'pink' },
  face: { icon: '☾', path: '/face', color: 'blue' },
};

export default function MyPage() {
  const [name, setName] = useState(() => localStorage.getItem('myohan-profile-name') || '묘한 손님');
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(name);
  const [history, setHistory] = useState(() => JSON.parse(localStorage.getItem('myohan-fortune-history') || '[]'));

  function saveName(event) {
    event.preventDefault();
    const nextName = draft.trim() || '묘한 손님';
    setName(nextName);
    localStorage.setItem('myohan-profile-name', nextName);
    setEditing(false);
  }

  function clearHistory() {
    localStorage.removeItem('myohan-fortune-history');
    setHistory([]);
  }

  return <main className="mypage">
    <section className="mypage-hero">
      <div className="profile-avatar">ฅ</div>
      <div className="profile-copy"><span>MY PAGE</span>{editing
        ? <form onSubmit={saveName}><input autoFocus value={draft} onChange={(event) => setDraft(event.target.value)} maxLength="16"/><button type="submit">저장</button><button type="button" onClick={() => setEditing(false)}>취소</button></form>
        : <h1>{name}님, 반가워요 <button type="button" onClick={() => { setDraft(name); setEditing(true); }}>수정</button></h1>}
        <p>내가 만난 운세와 묘미의 이야기를 한곳에서 확인하세요.</p>
      </div>
      <div className="profile-stats"><div><b>{history.length}</b><span>본 운세</span></div><div><b>{new Set(history.map((item) => item.type)).size}</b><span>이용 서비스</span></div></div>
    </section>

    <section className="mypage-layout">
      <div className="mypage-main">
        <div className="mypage-title"><div><span>RECENT FORTUNE</span><h2>최근 본 운세</h2></div>{history.length > 0 && <button type="button" onClick={clearHistory}>기록 전체 삭제</button>}</div>
        {history.length > 0 ? <div className="history-list">{history.map((item) => {
          const meta = typeMeta[item.type] || typeMeta.saju;
          return <article className="history-card" key={item.id}><div className={`history-icon ${meta.color}`}>{meta.icon}</div><div><span>{item.title} · {new Date(item.date).toLocaleDateString('ko-KR')}</span><h3>{item.resultTitle}</h3><p>{item.result}</p></div><Link to={meta.path}>다시 보기 →</Link></article>;
        })}</div> : <div className="empty-history"><span>☾</span><h3>아직 만난 운세가 없어요</h3><p>오늘의 마음과 가장 가까운 방법으로 첫 이야기를 만나보세요.</p><Link to="/tarot">운세 보러 가기 →</Link></div>}
      </div>

      <aside className="mypage-side">
        <section><span>QUICK MENU</span><h2>새로운 운세 보기</h2><nav><Link to="/saju"><b>☯</b><div>사주 운세<small>오늘의 흐름 살펴보기</small></div><i>›</i></Link><Link to="/tarot"><b>✦</b><div>타로<small>마음의 카드 고르기</small></div><i>›</i></Link><Link to="/face"><b>☾</b><div>관상<small>나의 인상 발견하기</small></div><i>›</i></Link></nav></section>
        <section className="mypage-settings"><span>SETTINGS</span><h2>이용 설정</h2><label><div>운세 알림<small>오늘의 한마디를 알려드려요</small></div><input type="checkbox"/><i/></label><label><div>채팅 기록 저장<small>이 기기에 대화를 보관해요</small></div><input type="checkbox" defaultChecked/><i/></label><p>현재 프로필과 운세 기록은 이 브라우저에만 저장됩니다.</p></section>
      </aside>
    </section>
  </main>;
}
