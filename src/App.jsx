import { Link, NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import HomePage from './pages/home/HomePage.jsx';
import SajuPage from './pages/saju/SajuPage.jsx';
import TarotPage from './pages/tarot/TarotPage.jsx';
import FacePage from './pages/face/FacePage.jsx';
import MyPage from './pages/mypage/MyPage.jsx';
import ConversationDetailPage from './pages/mypage/ConversationDetailPage.jsx';
import AuthPage from './pages/auth/AuthPage.jsx';
import DashboardPage from './pages/dashboard/DashboardPage.jsx';
import { useAuth } from './auth/AuthContext.jsx';

function Header() {
  const { user, logout } = useAuth();
  const nav = [['홈', '/'], ['사주', '/saju'], ['타로', '/tarot'], ['관상', '/face']];
  return <header className="header"><div className="nav-wrap">
    <Link className="brand" to="/"><span className="paw">🐾</span><span>묘한운세</span><small>묘리가 들려주는<br />당신의 운명 이야기</small></Link>
    <nav>{nav.map(([label, path]) => <NavLink key={path} end={path === '/'} to={path}>{label}</NavLink>)}</nav>
    <div className="header-account">{user ? <>
      {user.role === 'admin' && <NavLink className="header-login" to="/dashboard">관리 대시보드</NavLink>}
      <NavLink className="header-cta" to="/mypage">마이페이지</NavLink><button type="button" onClick={logout}>로그아웃</button>
    </> : <><NavLink className="header-login" to="/login">로그인</NavLink><NavLink className="header-cta" to="/signup">회원가입</NavLink></>}</div>
  </div></header>;
}

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <main className="route-loading">계정 정보를 확인하고 있어요.</main>;
  return user ? children : <Navigate to="/login" replace state={{ from: location.pathname }} />;
}

function AdminRoute({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <main className="route-loading">권한을 확인하고 있어요.</main>;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return user.role === 'admin' ? children : <Navigate to="/" replace />;
}

function Footer() { return <footer id="community"><div><Link className="footer-brand" to="/">🐾 묘한운세</Link><p>묘리가 들려주는 당신의 운명 이야기</p></div><div className="footer-links"><a href="#guide">이용안내</a><a href="#community">커뮤니티</a><a href="mailto:hello@myohan.example">고객센터</a></div><small>© 2026 MYOHANUNSE. All rights reserved.</small></footer>; }

export default function App() {
  return <><Header /><Routes>
    <Route path="/" element={<HomePage />} /><Route path="/saju" element={<SajuPage />} />
    <Route path="/tarot" element={<TarotPage />} /><Route path="/face" element={<FacePage />} />
    <Route path="/login" element={<AuthPage mode="login" />} /><Route path="/signup" element={<AuthPage mode="signup" />} />
    <Route path="/mypage" element={<ProtectedRoute><MyPage /></ProtectedRoute>} />
    <Route path="/mypage/conversations/:service/:readingId" element={<ProtectedRoute><ConversationDetailPage /></ProtectedRoute>} />
    <Route path="/dashboard" element={<AdminRoute><DashboardPage /></AdminRoute>} />
    <Route path="*" element={<HomePage />} />
  </Routes><Footer /></>;
}
