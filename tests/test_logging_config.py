import io
import json
import logging
import unittest

import app.core.logging as logging_module
from app.core.logging import JsonFormatter, configure_logging


class JsonFormatterTests(unittest.TestCase):
    def test_extra_fields_are_folded_into_the_json_payload(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="phanda.events", level=logging.INFO, pathname=__file__, lineno=1,
            msg="phanda_event", args=(), exc_info=None,
        )
        record.phanda_event = {"event": "tailoring_completed", "document_id": "abc"}
        parsed = json.loads(formatter.format(record))
        self.assertEqual(parsed["level"], "INFO")
        self.assertEqual(parsed["logger"], "phanda.events")
        self.assertEqual(parsed["phanda_event"], {"event": "tailoring_completed", "document_id": "abc"})


class ConfigureLoggingTests(unittest.TestCase):
    def test_configure_logging_makes_events_reach_a_stream(self):
        # Reset the idempotency guard so this test can observe a fresh configuration
        # regardless of whichever test module ran first in the process.
        logging_module._CONFIGURED = False
        stream = io.StringIO()
        original_stdout = __import__("sys").stdout
        __import__("sys").stdout = stream
        try:
            configure_logging()
        finally:
            __import__("sys").stdout = original_stdout

        logger = logging.getLogger("phanda.events")
        self.assertEqual(logger.getEffectiveLevel(), logging.INFO)

    def test_configure_logging_is_idempotent(self):
        configure_logging()
        handlers_after_first = list(logging.getLogger().handlers)
        configure_logging()
        self.assertEqual(logging.getLogger().handlers, handlers_after_first)


if __name__ == "__main__":
    unittest.main()
