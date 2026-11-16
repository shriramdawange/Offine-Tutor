import unittest
from unittest.mock import Mock, patch

from app import config
from app.main import _groq_chat_model_ids


class GroqModelCatalogTests(unittest.TestCase):
    def test_returns_only_chat_sized_text_models(self):
        response = Mock()
        response.json.return_value = {
            "data": [
                {"id": "llama-chat", "context_window": 8192},
                {"id": "whisper-large-v3", "context_window": 8192},
                {"id": "orpheus-voice", "context_window": 8192},
                {"id": "tiny-model", "context_window": 2048},
                {"id": "guard-model", "context_window": 8192},
                {"id": "mixtral-chat", "context_window": 32768},
            ]
        }
        with patch("requests.get", return_value=response) as get, \
             patch.object(config, "API_KEY", "test-key"):
            self.assertEqual(_groq_chat_model_ids(), ["llama-chat", "mixtral-chat"])
        get.assert_called_once()
        self.assertIn("Bearer test-key", get.call_args.kwargs["headers"]["Authorization"])

    def test_ignores_invalid_context_window_values(self):
        response = Mock()
        response.json.return_value = {
            "data": [
                {"id": "bad-metadata", "context_window": "unknown"},
                {"id": "valid-chat", "context_window": 4096},
            ]
        }
        with patch("requests.get", return_value=response):
            self.assertEqual(_groq_chat_model_ids(), ["valid-chat"])

    def test_rejects_unexpected_catalog_shape(self):
        response = Mock()
        response.json.return_value = {"models": []}
        with patch("requests.get", return_value=response):
            with self.assertRaises(ValueError):
                _groq_chat_model_ids()


if __name__ == "__main__":
    unittest.main()
