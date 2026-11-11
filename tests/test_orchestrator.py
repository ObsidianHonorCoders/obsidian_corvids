import copy
import unittest
from unittest.mock import Mock

from orchestrator import Limits, Orchestrator, TurnError, required_tools


def response(content="", calls=None):
    message = {"role": "assistant", "content": content}
    if calls is not None:
        message["tool_calls"] = calls
    return {"message": message}


def call(name="get_cfo_data", arguments=None):
    return {"function": {"name": name, "arguments": {} if arguments is None else arguments}}


class OrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.engine = Orchestrator(self.client, "test-model")

    def succeed(self, history=None):
        self.client.chat.side_effect = [response(calls=[call()]), response("Simulated finance summary")]
        return self.engine.run("Review finances", history or [])

    def test_success_and_request_limits(self):
        history = self.succeed()
        self.assertEqual(history[0].answer, "Simulated finance summary")
        self.assertEqual([message["role"] for message in history[0].messages], ["user", "assistant", "tool", "assistant"])
        self.assertEqual(self.client.chat.call_count, 2)
        kwargs = self.client.chat.call_args.kwargs
        self.assertNotIn("tools", kwargs)
        self.assertEqual(kwargs["options"]["num_predict"], 512)
        self.assertFalse(kwargs["stream"])

    def test_bad_arguments_do_not_mutate_history(self):
        history = self.succeed()
        snapshot = copy.deepcopy(history)
        self.client.chat.side_effect = [response(calls=[call(arguments={"unexpected": "value"})])]
        with self.assertRaises(TurnError):
            self.engine.run("Review finances again", history)
        self.assertEqual(history, snapshot)

    def test_synthesis_failure_does_not_mutate_history(self):
        history = self.succeed()
        snapshot = copy.deepcopy(history)
        self.client.chat.side_effect = [
            response(calls=[call()]),
            TimeoutError("private endpoint"),
        ]
        with self.assertRaises(TimeoutError):
            self.engine.run("Review finances again", history)
        self.assertEqual(history, snapshot)

    def test_unknown_duplicate_and_excessive_tools(self):
        for calls in ([call("exec")], [call(), call()], [call()] * 5):
            with self.subTest(calls=calls):
                self.client.chat.side_effect = [response(calls=calls)]
                with self.assertRaises(TurnError):
                    self.engine.run("Review", [])

    def test_domain_router_maps_explicit_and_broad_queries(self):
        self.assertEqual(required_tools("Review cash flow and security posture"), {"get_cfo_data", "get_ciso_data"})
        self.assertEqual(required_tools("How did the campaign perform?"), {"get_cmo_data"})
        self.assertEqual(required_tools("Give me an executive overview"), {
            "get_cfo_data", "get_ciso_data", "get_cmo_data", "get_coo_data",
        })

    def test_model_cannot_select_unrelated_tools(self):
        self.client.chat.side_effect = [response(calls=[call("get_cfo_data")])]
        with self.assertRaisesRegex(TurnError, "do not match"):
            self.engine.run("How did the marketing campaign perform?", [])

    def test_missing_tool_or_empty_answer_is_rejected(self):
        for responses in ([response("Unsupported direct answer")], [response(calls=[call()]), response("")]):
            self.client.chat.side_effect = responses
            with self.assertRaises(TurnError):
                self.engine.run("Review", [])

    def test_input_is_rejected_before_inference(self):
        for query in ("   ", "x" * 1501):
            with self.assertRaises(TurnError):
                self.engine.run(query, [])
        self.client.chat.assert_not_called()

    def test_history_retains_only_complete_bounded_turns(self):
        self.engine = Orchestrator(self.client, "test", Limits(history_turns=2))
        history = []
        for _ in range(5):
            history = self.succeed(history)
        self.assertEqual(len(history), 2)
        self.assertTrue(all(turn.messages[-1]["role"] == "assistant" for turn in history))


if __name__ == "__main__":
    unittest.main()