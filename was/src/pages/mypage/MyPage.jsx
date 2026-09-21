import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { listMyConversations } from '../../lib/api.js';
import { useAuth } from '../../auth/AuthContext.jsx';
import { conversationServiceMeta as typeMeta, toHistoryItem } from './conversationView.js';
import './mypage.css';

export default function MyPage() {
  const { user } = useAuth();
  const [server, setServer] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [nextCursor, setNextCursor] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    listMyConversations()
      .then((page) => {
        if (!alive) return;
        setServer(page.items.map(toHistoryItem));
        setNextCursor(page.next_cursor);
      })
      .catch((failure) => alive && setError(failure.message))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, []);

  const loadMore = async () => {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    setError('');
    try {
      const page = await listMyConversations({ cursor: nextCursor });
      setServer((current) => [...current, ...page.items.map(toHistoryItem)]);
      setNextCursor(page.next_cursor);
    } catch (failure) {
      setError(failure.message);
    } finally {
      setLoadingMore(false);
    }
  };

  const history = server;

  return <main className="mypage">
    <section className="mypage-hero">
      <div className="profile-avatar">ฅ</div>
      <div className="profile-copy"><span>MY PAGE</span><h1>{user.name}님, 반가워요</h1>
        <p>@{user.username} · {user.email}</p>
      </div>
      <div className="profile-stats"><div><b>{history.length}</b><span>본 운세</span></div><div><b>{new Set(history.map((item) => item.type)).size}</b><span>이용 서비스</span></div></div>
    </section>

    <section className="mypage-layout">
      <div className="mypage-main">
        <div className="mypage-title">
          <div><span>RECENT FORTUNE</span><h2>최근 본 운세</h2></div>
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
                  <Link to={item.detailPath}>대화 보기 →</Link>
                </article>;
              })}</div>
              {nextCursor && <button className="history-more" type="button" onClick={loadMore} disabled={loadingMore}>{loadingMore ? '불러오는 중…' : '더 보기'}</button>}
              {error && <p className="history-notice warn">기록을 더 불러오지 못했어요. {error}</p>}
              </>
            : <div className="empty-history"><span>☾</span><h3>아직 만난 운세가 없어요</h3><p>{error || '오늘의 마음과 가장 가까운 방법으로 첫 이야기를 만나보세요.'}</p><Link to="/tarot">운세 보러 가기 →</Link></div>}
      </div>

      <aside className="mypage-side">
        <section><span>QUICK MENU</span><h2>새로운 운세 보기</h2><nav><Link to="/saju"><b>☯</b><div>사주 운세<small>오늘의 흐름 살펴보기</small></div><i>›</i></Link><Link to="/tarot"><b>✦</b><div>타로<small>마음의 카드 고르기</small></div><i>›</i></Link><Link to="/face"><b>☾</b><div>관상<small>나의 인상 발견하기</small></div><i>›</i></Link></nav></section>
        <section className="mypage-settings"><span>SETTINGS</span><h2>이용 설정</h2><label><div>운세 알림<small>오늘의 한마디를 알려드려요</small></div><input type="checkbox"/><i/></label><label><div>채팅 기록 저장<small>이 기기에 대화를 보관해요</small></div><input type="checkbox" defaultChecked/><i/></label>
          <p>사주·타로·관상 기록은 로그인한 계정에 안전하게 분리되어 저장돼요. 다른 기기에서도 같은 계정으로 로그인하면 기록을 이어볼 수 있어요.</p>
        </section>
      </aside>
    </section>
  </main>;
}
