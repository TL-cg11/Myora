import './saju-meaning.css';

const positions = { year: '年柱', month: '月柱', day: '日柱', hour: '時柱' };

function Term({ term }) {
  return <p><strong>{term.name_ko} ({term.hanja})</strong>: {term.meaning_ko}</p>;
}

function DictionaryMeaning({ interpretation }) {
  const { concepts, pillars, day_stem, jeonggyeok, yongsin, sinsal } = interpretation;
  return <div className="saju-meanings">
    {pillars.map((pillar) => <section key={pillar.position}>
      <h3>{concepts[positions[pillar.position]].name_ko} · {pillar.term.name_ko} ({pillar.term.hanja})</h3>
      <p>{concepts[positions[pillar.position]].meaning_ko}</p>
      <p>{pillar.term.meaning_ko}</p>
      <Term term={pillar.stem} /><Term term={pillar.branch} />
    </section>)}
    <h3>{concepts['日干'].name_ko}</h3><p>{concepts['日干'].meaning_ko}</p><Term term={day_stem} />
    <h3>{concepts['正格'].name_ko}</h3><p>{concepts['正格'].meaning_ko}</p><Term term={jeonggyeok} />
    <h3>{concepts['用神'].name_ko}</h3><p>{concepts['用神'].meaning_ko}</p>
    <Term term={yongsin.element} /><Term term={yongsin.method} />
    {yongsin.auxiliary_element && <><h4>보조 용신</h4><Term term={yongsin.auxiliary_element} />
      {yongsin.auxiliary_method && <Term term={yongsin.auxiliary_method} />}</>}
    <h3>{concepts['神殺'].name_ko}</h3><p>{concepts['神殺'].meaning_ko}</p>
    {sinsal.length ? sinsal.map((item, index) => <div key={`${item.term.hanja}-${index}`}>
      <Term term={item.term} /><p>해당 위치: {item.locations.join(', ')}</p>
    </div>) : <p>해당하는 신살이 없습니다.</p>}
  </div>;
}

export default function SajuMeaning({ interpretation }) {
  const story = interpretation.narrative;
  if (!story) return <DictionaryMeaning interpretation={interpretation} />;
  return <div className="saju-story">
    <header className="saju-story-intro">
      <span className="saju-story-eyebrow">{story.subtitle}</span>
      <h3>{story.title}</h3>
      <div className="saju-story-keywords" aria-label="나의 기질 키워드">
        {story.profile.keywords.map((keyword) => <span key={keyword}>#{keyword}</span>)}
      </div>
      {story.overview.map((text, index) => <p key={index}>{text}</p>)}
    </header>
    <div className="saju-story-pillars" aria-label="사주 원국 요약">
      {interpretation.pillars.map((pillar) => <div key={pillar.position}>
        <small>{interpretation.concepts[positions[pillar.position]].name_ko}</small>
        <strong>{pillar.term.name_ko}</strong><span>{pillar.term.hanja}</span>
      </div>)}
    </div>
    {story.sections.map((section) => <section key={section.id} className="saju-story-section">
      <h3>{section.title}</h3>
      {section.keywords.length > 0 && <div className="saju-story-tags">{section.keywords.map((text) => <span key={text}>{text}</span>)}</div>}
      {section.paragraphs.map((text, index) => <p key={index}>{text}</p>)}
    </section>)}
    {story.supporting.length > 0 && <section className="saju-story-section saju-story-advice">
      <h3>이런 점도 함께 살펴보세요</h3>
      {story.supporting.map((item, index) => <div key={index}><p>{item.text}</p><small>{item.name} · {item.locations.join(', ')}</small></div>)}
    </section>}
    <p className="saju-story-notice">{story.notice}</p>
    <details className="saju-story-details"><summary>풀이의 바탕이 된 한자와 용어 보기</summary><DictionaryMeaning interpretation={interpretation} /></details>
  </div>;
}
