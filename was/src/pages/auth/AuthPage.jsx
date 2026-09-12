import { useState } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext.jsx';
import './auth.css';

export default function AuthPage({ mode }) {
  const signup = mode === 'signup';
  const { user, login, register } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  if (user) return <Navigate to="/mypage" replace />;

  async function submit(event) {
    event.preventDefault();
    const form = Object.fromEntries(new FormData(event.currentTarget));
    if (signup && form.password !== form.passwordConfirm) {
      setError('비밀번호 확인이 일치하지 않아요.'); return;
    }
    setSubmitting(true); setError('');
    try {
      if (signup) await register(form);
      else await login({ loginId: form.loginId, password: form.password });
      navigate(location.state?.from || '/mypage', { replace: true });
    } catch (caught) {
      setError(caught.message);
    } finally { setSubmitting(false); }
  }

  return <main className="auth-page">
    <section className="auth-card">
      <div className="auth-symbol">ฅ</div>
      <span>{signup ? 'JOIN MYOHAN' : 'WELCOME BACK'}</span>
      <h1>{signup ? '묘한운세와 첫 인사를 나눠요' : '다시 만나서 반가워요'}</h1>
      <p>{signup ? '계정을 만들면 어느 기기에서든 나의 운세 기록을 이어볼 수 있어요.' : '내 계정으로 운세 기록과 묘라의 이야기를 이어보세요.'}</p>
      <form onSubmit={submit}>
        {signup && <>
          <label>아이디<input name="username" required minLength="4" maxLength="40" pattern="[A-Za-z0-9_]+" autoComplete="username" placeholder="영문, 숫자, 밑줄 4자 이상" /></label>
          <label>이름<input name="name" required maxLength="40" autoComplete="name" placeholder="이름을 입력해 주세요" /></label>
          <label>이메일<input name="email" required type="email" maxLength="190" autoComplete="email" placeholder="hello@example.com" /></label>
        </>}
        {!signup && <label>아이디 또는 이메일<input name="loginId" required autoComplete="username" placeholder="아이디 또는 이메일" /></label>}
        <label>비밀번호<input name="password" required type="password" minLength={signup ? 8 : 1} maxLength="128" autoComplete={signup ? 'new-password' : 'current-password'} placeholder={signup ? '8자 이상 입력해 주세요' : '비밀번호'} /></label>
        {signup && <label>비밀번호 확인<input name="passwordConfirm" required type="password" minLength="8" maxLength="128" autoComplete="new-password" placeholder="비밀번호를 다시 입력해 주세요" /></label>}
        {error && <p className="auth-error" role="alert">{error}</p>}
        <button type="submit" disabled={submitting}>{submitting ? '잠시만 기다려 주세요…' : signup ? '회원가입' : '로그인'}</button>
      </form>
      <div className="auth-switch">{signup ? '이미 계정이 있나요?' : '아직 계정이 없나요?'} <Link to={signup ? '/login' : '/signup'}>{signup ? '로그인' : '회원가입'}</Link></div>
    </section>
  </main>;
}
