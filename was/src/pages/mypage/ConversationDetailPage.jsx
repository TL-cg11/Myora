import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getMyConversation } from '../../lib/api.js';
import { maskForDisplay } from '../../lib/privacy.js';
import { conversationServiceMeta } from './conversationView.js';
import './conversation-detail.css';

function formatDate(value) {
  if (!value) return '';
  return new Date(value).toLocaleString('ko-KR', {
    year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

export default function ConversationDetailPage() {
  const { service, readingId } = useParams();
  const [conversation, setConversation] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const meta = conversationServiceMeta[service];

  useEffect(() => {
    let alive = true;
    const numericId = Number(readingId);
    if (!meta || !Number.isInteger(numericId) || numericId < 1) {
      setError('올바르지 않은 대화 주소예요.');
      setLoading(false);
      return () => { alive = false; };
    }
    getMyConversation(service, numericId)
      .then((value) => alive && setConversation(value))
      .catch((failure) => {
        if (!alive) return;
        setError(failure.status === 404 ? '대화 기록을 찾을 수 없어요.' : failure.message);
      })
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [meta, readingId, service]);

  if (loading) return <main className="conversation-page"><div className="conversation-state">대화 기록을 불러오는 중이에요…</div></main>;
  if (error) return <main className="conversation-page"><div className="conversation-state error"><span>☾</span><h1>{error}</h1><Link to="/mypage">마이페이지로 돌아가기</Link></div></main>;

  return <main className="conversation-page">
    <div className="conversation-shell">
      <Link className="conversation-back" to="/mypage">← 최근 본 운세</Link>
      <section className="conversation-result">
        <div className={`conversation-service ${meta.color}`}>{meta.icon}</div>
        <div className="conversation-result-copy">
          <span>{meta.label} 상담 · {formatDate(conversation.created_at)}</span>
          <h1>{conversation.result.title || `${meta.label} 결과`}</h1>
          <p>{conversation.result.summary || '저장된 결과 요약이 없어요.'}</p>
        </div>
      </section>

      <section className="conversation-history">
        <header><div><span>CONVERSATION</span><h2>나눈 대화</h2></div><b>{conversation.message_count}개</b></header>
        {conversation.messages.length === 0
          ? <div className="conversation-empty"><span>✦</span><h3>아직 나눈 대화가 없어요</h3><p>저장된 운세 결과는 위에서 다시 볼 수 있어요.</p></div>
          : <ol className="conversation-messages">{conversation.messages.map((message) => <li className={`conversation-message ${message.role}`} key={`${message.seq}-${message.role}`}>
              <div className="message-meta"><b>{message.role === 'user' ? '나' : message.role === 'assistant' ? '묘라' : '안내'}</b><time>{formatDate(message.created_at)}</time></div>
              <p>{message.role === 'user' ? maskForDisplay(message.content) : message.content}</p>
            </li>)}</ol>}
      </section>

      <div className="conversation-actions"><Link to={meta.path}>새로운 {meta.label} 보기</Link><Link to="/mypage">목록으로 돌아가기</Link></div>
    </div>
  </main>;
}
