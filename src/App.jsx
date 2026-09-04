import { Link, NavLink, Route, Routes } from 'react-router-dom';
import HomePage from './pages/home/HomePage.jsx';
import SajuPage from './pages/saju/SajuPage.jsx';
import TarotPage from './pages/tarot/TarotPage.jsx';
import FacePage from './pages/face/FacePage.jsx';
import MyPage from './pages/mypage/MyPage.jsx';

function Header() {
  const nav = [['홈','/'],['사주','/saju'],['타로','/tarot'],['관상','/face']];
  return <header className="header"><div className="nav-wrap"><Link className="brand" to="/"><span className="paw">✿</span><span>묘한운세</span><small>묘라가 전해주는<br/>당신의 운명 이야기</small></Link><nav>{nav.map(([label,path])=><NavLink key={path} end={path === '/'} to={path}>{label}</NavLink>)}</nav><NavLink className="header-cta" to="/mypage">마이페이지</NavLink></div></header>;
}

function Footer(){return <footer id="community"><div><Link className="footer-brand" to="/">✿ 묘한운세</Link><p>묘라가 전해주는 당신의 운명 이야기</p></div><div className="footer-links"><a href="#guide">이용안내</a><a href="#community">커뮤니티</a><a href="mailto:hello@myohan.example">고객센터</a></div><small>© 2026 MYOHANUNSE. All rights reserved.</small></footer>}
export default function App(){return <><Header/><Routes><Route path="/" element={<HomePage/>}/><Route path="/saju" element={<SajuPage/>}/><Route path="/tarot" element={<TarotPage/>}/><Route path="/face" element={<FacePage/>}/><Route path="/mypage" element={<MyPage/>}/><Route path="*" element={<HomePage/>}/></Routes><Footer/></>}
