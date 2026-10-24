import unittest
from unittest.mock import patch

from app import config, llm


class LLMRoutingTests(unittest.TestCase):
    def test_cloud_failure_falls_back_to_local(self):
        with patch.object(config, "LLM_PROVIDER", "auto"), \
             patch.object(config, "API_KEY", "test-key"), \
             patch.object(llm, "_cloud_complete", side_effect=llm.LLMError("offline")), \
             patch.object(llm, "_local_stream", return_value=iter(["local ", "answer"])):
            self.assertEqual("".join(llm.stream_chat([{"role": "user", "content": "hi"}])), "local answer")

    def test_cloud_success_does_not_call_local(self):
        with patch.object(config, "LLM_PROVIDER", "auto"), \
             patch.object(config, "API_KEY", "test-key"), \
             patch.object(llm, "_cloud_complete", return_value="cloud answer"), \
             patch.object(llm, "_local_stream") as local:
            self.assertEqual("".join(llm.stream_chat([{"role": "user", "content": "hi"}])), "cloud answer")
            local.assert_not_called()

    def test_local_mode_skips_cloud(self):
        with patch.object(config, "LLM_PROVIDER", "local"), \
             patch.object(config, "API_KEY", "test-key"), \
             patch.object(llm, "_cloud_complete") as cloud, \
             patch.object(llm, "_local_stream", return_value=iter(["local"])):
            self.assertEqual("".join(llm.stream_chat([{"role": "user", "content": "hi"}])), "local")
            cloud.assert_not_called()


if __name__ == "__main__":
    unittest.main()
