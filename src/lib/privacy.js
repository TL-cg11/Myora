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
