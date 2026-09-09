# 소비자 계약 사본

`luck-nginx/contracts`에서 복사한 C 담당 계약 v1이다. 어댑터가 발행하는 결과 메시지를
같은 저장소 안에서 검증하기 위해 둔 사본이며 원본은 `luck-nginx` 저장소가 관리한다.

| 파일 | Topic | 소비 대상 |
|---|---|---|
| `luck.masked-logs.v1.schema.json` | `myohan.masked-logs` | Loki |
| `luck.security-events.v1.schema.json` | `myohan.security-events` | `security_monitoring` DB |

원본이 바뀌면 이 사본과 `tests/test_adapter_contract.py`를 함께 갱신한다.
어댑터가 발행하는 실패 메시지 계약은 `../v1/kafka-dead-letter.schema.json`에 있다.
