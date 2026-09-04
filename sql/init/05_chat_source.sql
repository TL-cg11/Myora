-- 채팅 답변의 출처를 남긴다.
-- 적용: sudo mysql -uroot luck_db < sql/init/05_chat_source.sql
--
-- DeepSeek 이 붙었지만 어떤 답변이 LLM 이고 어떤 게 규칙 기반 폴백인지 저장하지
-- 않아서, 나중에 답변 품질을 되짚을 방법이 없다. 이 한 칼럼이 그걸 메운다.
-- 스키마 재설계(공통 reading 구조)와는 무관하게 지금 적용할 수 있다.
--
-- ADD COLUMN IF NOT EXISTS 라 다시 실행해도 안전하다.
-- 기존 행은 NULL 로 남는다. 그때는 기록하지 않았다는 뜻이고, 'rule' 로 채우면
-- 실제로는 LLM 이었을 수도 있는 답변까지 규칙 기반으로 단정하게 되므로 두지 않는다.

ALTER TABLE tarot_chat_message
  ADD COLUMN IF NOT EXISTS source ENUM('rule','llm') NULL
  COMMENT 'assistant 답변을 무엇으로 만들었나. user/system 메시지는 NULL'
  AFTER content;
