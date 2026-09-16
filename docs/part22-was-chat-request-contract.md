# Part 22 WAS chat-request contract

The Nginx notifier and the Consumer · masked logs dashboard use only detector
output with `source_type=chat_request`. The detector adapter preserves the WAS
`event_type` in this field, so no Kafka topic or detector schema change is
required.

The WAS owner must emit `chat_request` after all prechecks and after the user
question row is committed, immediately before the real AI/guardrail call. Do
not emit it for question-limit 429, missing reading, authorization rejection,
or failed DB reservation. Emit `chat_response` only after the final response is
stored; it remains in the ordinary masking/Loki flow but is excluded from the
new Discord alert and the request-log panel.

Log-emission failures must stay non-blocking for the chat API. Both messages
must retain the same `request_id`; their distinct `event_type` values must be
preserved through detector output as `source_type`.
