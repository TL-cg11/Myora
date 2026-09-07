const positions = { year: '年柱', month: '月柱', day: '日柱', hour: '時柱' };

function Term({ term }) {
  return <p><strong>{term.name_ko} ({term.hanja})</strong>: {term.meaning_ko}</p>;
}

export default function SajuMeaning({ interpretation }) {
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
