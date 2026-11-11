import runpy
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def model_response(content="", calls=None):
    message = {"role": "assistant", "content": content}
    if calls is not None:
        message["tool_calls"] = calls
    return {"message": message}


class State(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as error:
            raise AttributeError(name) from error

    def __setattr__(self, name, value):
        self[name] = value


class AppTests(unittest.TestCase):
    def test_chat_renders_only_user_and_final_answer_across_reruns(self):
        ui = MagicMock()
        ui.cache_resource.side_effect = lambda function: function
        ui.session_state = State()
        ui.context = SimpleNamespace(headers={})
        ui.chat_input.return_value = "Review finances"

        client = MagicMock()
        client.chat.side_effect = [
            model_response(calls=[{"function": {"name": "get_cfo_data", "arguments": {}}}]),
            model_response("This is a simulated finance summary."),
        ]
        ollama = MagicMock()
        ollama.Client.return_value = client

        with patch.dict(os.environ, {"APP_ENV": "development"}), patch.dict(
            sys.modules, {"streamlit": ui, "ollama": ollama}
        ):
            runpy.run_path("app.py")

        self.assertEqual(len(ui.session_state.chat_history), 1)
        self.assertEqual(ui.session_state.chat_history[0].answer, "This is a simulated finance summary.")
        self.assertEqual(ui.markdown.call_args_list[-1].args[0], "This is a simulated finance summary.")

        ui.chat_input.return_value = None
        with patch.dict(os.environ, {"APP_ENV": "development"}), patch.dict(
            sys.modules, {"streamlit": ui, "ollama": ollama}
        ):
            runpy.run_path("app.py")
        rendered = [call.args[0] for call in ui.markdown.call_args_list]
        self.assertEqual(rendered[-2:], ["Review finances", "This is a simulated finance summary."])
        self.assertTrue(all("cash_flow" not in text for text in rendered))


if __name__ == "__main__":
    unittest.main()