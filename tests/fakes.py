"""Test doubles for the chat model, so no test needs an API key."""


class FakeStructuredLLM:
    """Stands in for llm.with_structured_output(...): returns canned results in order."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def with_structured_output(self, schema):
        return self

    def invoke(self, messages):
        self.calls.append(messages)
        return self.results.pop(0)
