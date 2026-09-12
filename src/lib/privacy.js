/** 화면에서 미리 걸러 주기 위한 정형 식별자 검사.
 *
 *  실제 차단은 서버(app/services/guardrail.py 의 DIRECT_IDENTIFIER_PATTERNS)가 한다.
 *  여기는 사용자가 입력 화면을 떠나기 전에 알려 주기 위한 것이므로, 서버보다
 *  느슨해도(놓쳐도) 서버가 잡는다. 반대로 서버보다 엄격해지면 정상 질문을 막게
 *  되므로 패턴을 임의로 넓히지 않는다.
 */
const DIRECT_IDENTIFIER_PATTERNS = [
  /[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}/,
  /(?<!\d)\d{6}\s*-\s*[1-4]\d{6}(?!\d)/,
  /(?<!\d)(?:\+82[- .]?)?0?1[016789][- .]?\d{3,4}[- .]?\d{4}(?!\d)/,
  /https?:\/\/\S+/,
  /\bsk-[A-Za-z0-9_-]+\b/,
];

export const DIRECT_IDENTIFIER_MESSAGE =
  '질문에 이메일·전화번호·주민등록번호·링크는 빼고 적어주세요.';

export function hasDirectIdentifier(text) {
  return typeof text === 'string' && DIRECT_IDENTIFIER_PATTERNS.some((pattern) => pattern.test(text));
}

/** 서버(app/services/profanity.py)와 같은 범위의 거친 표현.
 *  서버가 저장·응답에서 이미 가리므로, 여기는 아직 서버를 거치지 않은
 *  낙관적 말풍선을 위한 것이다. */
const PROFANITY = /[시씨]+[1발벌바빠]+[랄로]?(?![점역차])|ㅅ+ㅂ+|[좆좃존]같|[개게]새+[끼키기]|병+신+|지+랄+|존나+|[엿옘]같|[씹씨]+[발빨]|미친[놈년]|[꺼거]져|닥쳐|fuck\w*|shit\w*|bitch\w*/gi;

/** 눈으로 구분되지 않는 회피를 펴 준다. 서버(profanity.normalize)와 같은 범위다. */
const INVISIBLE = /[\u200b-\u200f\u2060\ufeff]/g;

/** 서버로 보내는 원문은 바꾸지 않고 사용자 말풍선에 표시할 문자열만 가린다. */
export function maskForDisplay(text) {
  if (typeof text !== 'string') return text;
  return finishContextualDisplay(text
    .normalize('NFKC')
    .replace(INVISIBLE, '')
    .replace(/[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}/g, (value) => {
      const [local, domain] = value.split('@');
      return `${local.slice(0, 1)}***@${domain}`;
    })
    .replace(/(?<!\d)\d{6}\s*-\s*[1-4]\d{6}(?!\d)/g, '******-*******')
    .replace(/(?<!\d)(?:\+82[- .]?)?0?1[016789][- .]?\d{3,4}[- .]?\d{4}(?!\d)/g, (value) => {
      const digits = value.replace(/\D/g, '').replace(/^82/, '0');
      return `${digits.slice(0, 3)}-****-${digits.slice(-4)}`;
    })
    .replace(/https?:\/\/\S+/g, '[비공개 링크]')
    .replace(/\bsk-[A-Za-z0-9_-]+\b/g, '[비공개 키]'));
}

/** 서버의 문맥 모델이 처리한 결과에 화면 전용 링크·비속어 정책만 추가한다. */
export function finishContextualDisplay(text) {
  if (typeof text !== 'string') return text;
  return text
    .normalize('NFKC')
    .replace(INVISIBLE, '')
    .replace(/https?:\/\/\S+/g, '[비공개 링크]')
    .replace(/\bsk-[A-Za-z0-9_-]+\b/g, '[비공개 키]')
    .replace(PROFANITY, (value) => '■'.repeat(Math.max(2, value.length)));
}
