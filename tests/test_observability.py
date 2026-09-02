import unittest
import uuid

from app.core.observability import emit_event


class ObservabilityTests(unittest.TestCase):
    def test_event_contains_only_scalar_operational_metadata(self):
        document_id = uuid.uuid4()
        with self.assertLogs("phanda.events", level="INFO") as captured:
            emit_event("tailoring_completed", document_id=document_id, attempt=1)
        payload = captured.records[0].phanda_event
        self.assertEqual(payload["event"], "tailoring_completed")
        self.assertEqual(payload["document_id"], str(document_id))
        self.assertEqual(payload["attempt"], 1)

    def test_rejects_structured_payloads_that_could_contain_pii(self):
        with self.assertRaises(TypeError):
            emit_event("tailoring_failed", provider_response={"candidate_cv": "private"})
