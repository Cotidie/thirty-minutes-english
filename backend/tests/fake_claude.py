"""A stand-in for claude_agent_sdk.query that replays messages."""

from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock


def result(structured_output=None, is_error=False, text=None) -> ResultMessage:
    return ResultMessage(
        subtype="error_during_execution" if is_error else "success",
        duration_ms=1200,
        duration_api_ms=1000,
        is_error=is_error,
        num_turns=2,
        session_id="s",
        result=text,
        structured_output=structured_output,
        total_cost_usd=0.01,
    )


def assistant(*blocks) -> AssistantMessage:
    return AssistantMessage(content=list(blocks), model="opus")


def tool_use(name: str) -> ToolUseBlock:
    return ToolUseBlock(id=name, name=name, input={})


def text(value: str = "...") -> TextBlock:
    return TextBlock(text=value)


class FakeQuery:
    """Records the options of each call and yields the given messages."""

    def __init__(self, *messages, error: Exception | None = None, hang: bool = False):
        self.messages = messages
        self.error = error
        self.hang = hang
        self.calls: list = []

    async def __call__(self, *, prompt, options):
        import asyncio

        self.calls.append((prompt, options))
        if self.error:
            raise self.error
        if self.hang:
            await asyncio.sleep(10)
        for message in self.messages:
            yield message
