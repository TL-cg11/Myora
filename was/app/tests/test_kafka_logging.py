import json
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import kafka_logging
from app.kafka_logging import api_request_log_middleware


class FakeProducer:
    def __init__(self) -> None:
        self.messages = []
        self.polled = []

    def produce(self, topic, **kwargs) -> None:
        self.messages.append((topic, kwargs))

    def poll(self, timeout) -> None:
        self.polled.append(timeout)

    def flush(self, timeout) -> int:
        return 0


class WasLoggingTest(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()
        app.middleware("http")(api_request_log_middleware)

        @app.post("/api/tarot/readings")
        def tarot_reading() -> dict:
            return {"id": 1}

        @app.get("/api/health")
        def health() -> dict:
            return {"status": "ok"}

        @app.get("/api/saju/failure")
        def failure() -> None:
            raise RuntimeError("test failure")

        @app.post("/api/tarot/readings/{reading_id}/chat")
        def tarot_chat(reading_id: int) -> dict:
            return {"answer": "ok"}

        @app.post("/api/saju/chat")
        def saju_chat_failure() -> None:
            raise RuntimeError("chat failure")

        @app.post("/api/face/chat-test")
        def ai_request() -> dict:
            kafka_logging.emit_ai_request_log(
                feature="face",
                question="관상 질문",
                model="deepseek-v4-flash",
                timeout_seconds=45,
            )
            return {"answer": "test"}

        self.client = TestClient(app)

    @patch("app.kafka_logging.emit_was_log")
    def test_emits_schema_shaped_api_request_log(self, emit) -> None:
        response = self.client.post(
            "/api/tarot/readings",
            headers={
                "X-Request-ID": "nginx-request-id",
                "X-Forwarded-For": "203.0.113.10, 127.0.0.1",
            },
            json={
                "guest_key": "3889ff5a-cadb-4c20-8759-083cac443121",
                "topic": "love",
                "question": "제 연애운이 어떻게 될까요?",
                "password": "must-not-be-logged",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Request-ID"], "nginx-request-id")
        event = emit.call_args.args[0]
        self.assertEqual(event["service"], "luck-was")
        self.assertEqual(event["feature"], "tarot")
        self.assertEqual(event["event_type"], "api_request")
        self.assertEqual(event["client_ip"], "203.0.113.10")
        self.assertEqual(event["input"], {"topic": "love", "question": "제 연애운이 어떻게 될까요?"})
        self.assertNotIn("password", json.dumps(event, ensure_ascii=False))

    @patch("app.kafka_logging.emit_was_log")
    def test_skips_api_request_log_on_success_for_chat_path(self, emit) -> None:
        """chat_request/chat_response가 같은 질문을 이미 남기므로, 성공한
        채팅 전송 요청은 api_request 로그를 중복으로 남기지 않는다."""
        response = self.client.post("/api/tarot/readings/1/chat", json={"message": "안녕"})

        self.assertEqual(response.status_code, 200)
        emit.assert_not_called()

    @patch("app.kafka_logging.emit_was_log")
    def test_still_emits_api_request_log_on_chat_failure(self, emit) -> None:
        """채팅 처리 중 예외가 나면 chat_request가 아예 안 남을 수 있으므로,
        실패한 요청은 그대로 api_request 로그를 남겨 감사 기록을 보존한다."""
        with self.assertRaises(RuntimeError):
            self.client.post("/api/saju/chat", json={"message": "안녕"})

        event = emit.call_args.args[0]
        self.assertEqual(event["event_type"], "api_request")
        self.assertEqual(event["status"], 500)

    @patch("app.kafka_logging.emit_was_log")
    def test_ignores_non_feature_endpoint(self, emit) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        emit.assert_not_called()

    @patch("app.kafka_logging.emit_was_log")
    def test_emits_log_for_unhandled_error(self, emit) -> None:
        with self.assertRaises(RuntimeError):
            self.client.get("/api/saju/failure")

        event = emit.call_args.args[0]
        self.assertEqual(event["feature"], "saju")
        self.assertEqual(event["status"], 500)
        self.assertEqual(event["severity"], "ERROR")

    def test_produces_json_to_was_topic_with_request_id_key(self) -> None:
        producer = FakeProducer()
        event = {"request_id": "request-1", "event_type": "api_request"}
        with patch.object(kafka_logging, "_producer", producer):
            kafka_logging.emit_was_log(event)

        topic, arguments = producer.messages[0]
        self.assertEqual(topic, "myohan.was.app")
        self.assertEqual(arguments["key"], "request-1")
        self.assertEqual(json.loads(arguments["value"]), event)
        self.assertEqual(producer.polled, [0])

    def test_builds_ai_request_without_full_context(self) -> None:
        event = kafka_logging.build_ai_request_log(
            feature="face",
            question="제 관상을 설명해 주세요",
            model="deepseek-v4-flash",
            timeout_seconds=45,
            message_count=3,
            context_length=1200,
        )

        self.assertEqual(event["feature"], "face")
        self.assertEqual(event["event_type"], "ai_request")
        self.assertEqual(event["ai"]["provider"], "deepseek")
        self.assertEqual(event["input"], {})
        self.assertEqual(event["metadata"]["context_length"], 1200)
        self.assertNotIn("context", event["input"])

    @patch("app.kafka_logging.emit_was_log")
    def test_chat_payload_and_final_answer_are_logged_separately(self, emit) -> None:
        response = self.client.post(
            "/api/face/chat-test",
            json={"message": "관상 질문"},
            headers={"X-Request-ID": "chat-request-id"},
        )
        self.assertEqual(response.status_code, 200)
        api_event = emit.call_args_list[-1].args[0]
        self.assertEqual(api_event["input"]["question"], "관상 질문")

        kafka_logging.emit_chat_exchange_log(
            feature="face",
            question="관상 질문",
            answer="답변에 010-1234-5678이 있습니다.",
            reading_id=7,
            generated=True,
        )
        request_event, response_event = (call.args[0] for call in emit.call_args_list[-2:])
        self.assertEqual(request_event["event_type"], "chat_request")
        self.assertEqual(request_event["input"], {"question": "관상 질문"})
        self.assertNotIn("output", request_event)
        self.assertEqual(response_event["event_type"], "chat_response")
        self.assertEqual(response_event["output"], {"answer": "답변에 010-1234-5678이 있습니다."})
        self.assertNotIn("input", response_event)
        self.assertEqual(request_event["request_id"], response_event["request_id"])
        self.assertEqual(
            response_event["metadata"]["answer_length"],
            len(response_event["output"]["answer"]),
        )

    def test_guardrail_decision_log_has_no_content(self) -> None:
        event = kafka_logging.build_guardrail_decision_log(
            feature="saju",
            decision="restrict",
            risk_level="HIGH",
            rules=["G04"],
            policy_version="1.1",
            phase="input",
        )

        self.assertEqual(event["event_type"], "ai_guardrail_decision")
        self.assertEqual(event["severity"], "WARNING")
        self.assertEqual(event["guardrail"]["rules"], ["G04"])
        self.assertNotIn("input", event)
        self.assertNotIn("content", json.dumps(event, ensure_ascii=False))

    @patch("app.kafka_logging.emit_was_log")
    def test_api_and_ai_events_share_request_id(self, emit) -> None:
        response = self.client.post(
            "/api/face/chat-test",
            headers={"X-Request-ID": "shared-request-id"},
        )

        self.assertEqual(response.status_code, 200)
        ai_event, api_event = (call.args[0] for call in emit.call_args_list)
        self.assertEqual(ai_event["event_type"], "ai_request")
        self.assertEqual(api_event["event_type"], "api_request")
        self.assertEqual(ai_event["request_id"], "shared-request-id")
        self.assertEqual(api_event["request_id"], "shared-request-id")


if __name__ == "__main__":
    unittest.main()
