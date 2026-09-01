import { Link, NavLink, Route, Routes } from 'react-router-dom';
import sajuCat from './assets/saju-cat.png';
import tarotCat from './assets/tarot-cat.png';
import faceCat from './assets/face-cat.png';
import threeCatsHero from './assets/three-cats-hero.png';
import FortuneExperience from './FortuneExperience.jsx';
import MyPage from './MyPage.jsx';
import './hero-three-cats.css';
import './fortune-experience.css';
import './mypage.css';

const services = [
  { title: '사주 운세', copy: '타고난 기운과 오늘의 흐름을\n차분하게 살펴보세요.', path: '/saju', image: sajuCat, tone: 'lilac', button: '사주 보기' },
  { title: '타로', copy: '마음속 질문을 떠올리고\n모미의 카드를 골라보세요.', path: '/tarot', image: tarotCat, tone: 'pink', button: '타로 보기' },
  { title: '관상', copy: '얼굴에 담긴 분위기와\n나만의 매력을 발견해요.', path: '/face', image: faceCat, tone: 'blue', button: '관상 보기' },
];

function Header() {
  const nav = [['홈','/'],['운세','/saju'],['타로','/tarot'],['관상','/face']];
  return <header className="header"><div className="nav-wrap"><Link className="brand" to="/"><span className="paw">✿</span><span>묘한운세</span><small>모미가 전해주는<br/>당신의 운명 이야기</small></Link><nav>{nav.map(([label,path])=><NavLink key={path} end={path === '/'} to={path}>{label}</NavLink>)}<a href="#today">오늘의 운세</a><a href="#guide">이용안내</a><a href="#community">커뮤니티</a></nav><NavLink className="header-cta" to="/mypage">마이페이지</NavLink></div></header>;
}

function Home() {
  return <main>
    <section className="hero"><i className="spark s1">✦</i><i className="spark s2">✧</i><i className="orb o1"/><i className="orb o2"/><div className="hero-inner"><div className="hero-copy"><span className="eyebrow">✦ 모미와 함께 알아보는 나의 이야기</span><h1>오늘도, 조금은<br/><strong>묘한 운세</strong></h1><p>사주 · 타로 · 관상으로 만나는<br/>나를 위한 다정한 운세 이야기</p><div className="hero-actions"><Link className="primary" to="/saju">오늘의 운세 보기 <b>→</b></Link><a className="text-link" href="#services">서비스 둘러보기</a></div></div><div className="hero-art hero-art-three"><img src={threeCatsHero} alt="사주, 타로, 관상을 상징하는 보라색 고양이 세 마리"/></div></div>
    </section>
    <section className="services section" id="services"><div className="section-head"><span>FORTUNE SERVICES</span><h2>오늘은 어떤 이야기가 궁금한가요?</h2><p>모미가 당신의 마음에 꼭 맞는 방법으로 이야기를 들려드릴게요.</p></div><div className="card-grid">{services.map((item)=><article className={`service-card ${item.tone}`} key={item.title}><div className="card-image"><img src={item.image} alt={`${item.title} 고양이 모미`}/></div><div className="card-body"><h3>{item.title}</h3><p>{item.copy}</p><Link to={item.path}>{item.button} <span>→</span></Link></div></article>)}</div></section>
    <section className="benefits section" id="guide"><div className="section-head"><span>WHY MYOHAN</span><h2>부담 없이 만나는 나의 운세</h2></div><div className="benefit-grid"><div><b>☾</b><h3>쉽고 편안하게</h3><p>어려운 말 대신 누구나 이해하기 쉽게 전해드려요.</p></div><div><b>✦</b><h3>나만을 위한 해석</h3><p>내 이야기에 집중한 다정하고 섬세한 풀이를 만나요.</p></div><div><b>♡</b><h3>따뜻한 한마디</h3><p>정답보다 오늘을 잘 보낼 수 있는 작은 용기를 드려요.</p></div><div><b>⌁</b><h3>언제 어디서나</h3><p>생각날 때 가볍게, 모바일에서도 편하게 이용해요.</p></div></div></section>
    <section className="closing" id="today"><div><span>오늘의 작은 선택이 내일의 행운이 될지도 몰라요</span><h2>모미와 함께, 당신의 이야기를 시작해볼까요?</h2><Link className="primary" to="/tarot">지금 운세 만나기 <b>→</b></Link></div><img src={sajuCat} alt="부채를 든 사주 고양이 모미"/></section>
  </main>;
}

function Footer(){return <footer id="community"><div><Link className="footer-brand" to="/">✿ 묘한운세</Link><p>모미가 전해주는 당신의 운명 이야기</p></div><div className="footer-links"><a href="#guide">이용안내</a><a href="#community">커뮤니티</a><a href="mailto:hello@myohan.example">고객센터</a></div><small>© 2026 MYOHANUNSE. All rights reserved.</small></footer>}
export default function App(){return <><Header/><Routes><Route path="/" element={<Home/>}/><Route path="/saju" element={<FortuneExperience type="saju" image={sajuCat}/>}/><Route path="/tarot" element={<FortuneExperience type="tarot" image={tarotCat}/>}/><Route path="/face" element={<FortuneExperience type="face" image={faceCat}/>}/><Route path="/mypage" element={<MyPage/>}/><Route path="*" element={<Home/>}/></Routes><Footer/></>}
