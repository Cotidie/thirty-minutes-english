import io
import re

from app.generation.korean_dialogues import SCHEMA, DialogueWriter, Filled, fill, prompt_for
from app.llm import GenerationError
from app.models import KoreanLine
from tests.conftest import seed_expressions


def two_lines(i: int) -> list[dict]:
    return [{"korean": f"가 {i}", "english": f"A {i}"}, {"korean": f"나 {i}", "english": f"B {i}"}]


class FakeClaude:
    """Answers each batch with two lines per id in the prompt. `answers` overrides the lines for an id ([] leaves it
    out); `extra` is appended as is; a batch holding an id in `fail` raises."""

    def __init__(self, answers=None, extra=(), fail=()):
        self.answers, self.extra, self.fail = answers or {}, list(extra), set(fail)
        self.batches: list[list[int]] = []
        self.schemas: list[dict] = []

    def run(self, prompt: str, schema: dict, on_message=None) -> dict:
        ids = [int(i) for i in re.findall(r'"id": (\d+)', prompt)]
        self.batches.append(ids)
        self.schemas.append(schema)
        if self.fail & set(ids):
            raise GenerationError("claude timed out after 300s")
        dialogues = [{"id": i, "lines": self.answers.get(i, two_lines(i))} for i in ids if self.answers.get(i, True) != []]
        return {"dialogues": dialogues + self.extra}


def run_fill(store, claude, *, limit=None, batch=20, apply=True) -> tuple[Filled, str]:
    out = io.StringIO()
    return fill(store.expressions, DialogueWriter(claude), limit=limit, batch=batch, apply=apply, out=out), out.getvalue()


def test_the_prompt_gives_each_expression_with_its_examples_and_korean_example(store):
    [a] = seed_expressions(store, 1)
    with store.connect() as conn:
        conn.execute("UPDATE expressions SET korean_example = ? WHERE id = ?", ('{"korean": "못 와?", "english": "Can\'t make it?"}', a))
    prompt = prompt_for([store.expressions.get(a)])
    for text in (f'"id": {a}', "alpha phrase", "meaning 0", "note 0", "ex 0a", "ex 0b", "못 와?"):
        assert text in prompt


def test_write_drops_blank_lines(store):
    a, b = seed_expressions(store, 2)
    claude = FakeClaude(answers={b: [{"korean": "가", "english": " "}, {"korean": "나", "english": "B"}]})
    written = DialogueWriter(claude).write([store.expressions.get(a), store.expressions.get(b)])
    assert list(written) == [a]
    assert written[a] == [KoreanLine(korean=f"가 {a}", english=f"A {a}"), KoreanLine(korean=f"나 {a}", english=f"B {a}")]


def test_write_drops_answers_without_exactly_two_lines(store):
    a, b, c = seed_expressions(store, 3)
    claude = FakeClaude(answers={b: two_lines(b)[:1], c: []})
    assert list(DialogueWriter(claude).write([store.expressions.get(i) for i in (a, b, c)])) == [a]


def test_write_keeps_only_the_first_answer_for_ids_it_asked_for(store):
    [a] = seed_expressions(store, 1)
    claude = FakeClaude(extra=[{"id": a, "lines": two_lines(99)}, {"id": 999, "lines": two_lines(999)}])
    written = DialogueWriter(claude).write([store.expressions.get(a)])
    assert list(written) == [a] and written[a][0].english == f"A {a}"


def test_a_preview_prints_each_dialogue_and_writes_nothing(store):
    a, b = seed_expressions(store, 2)
    filled, printed = run_fill(store, FakeClaude(), apply=False)
    assert filled == Filled(made=2, skipped=0)
    for text in ("alpha phrase", "bravo phrase", f"가 {a}", f"A {a}", f"나 {b}", f"B {b}", "nothing written"):
        assert text in printed
    assert [e.id for e in store.expressions.without_dialogue()] == [a, b]


def test_apply_asks_in_batches_and_writes_every_dialogue(store):
    ids = seed_expressions(store, 5)
    claude = FakeClaude()
    filled, _ = run_fill(store, claude, batch=2)
    assert claude.batches == [ids[:2], ids[2:4], ids[4:]]
    assert claude.schemas[0] is SCHEMA
    assert filled == Filled(made=5, skipped=0)
    assert store.expressions.without_dialogue() == []
    assert store.expressions.get(ids[4]).korean_dialogue[1].korean == f"나 {ids[4]}"


def test_a_failed_batch_is_skipped_and_the_others_are_written(store):
    ids = seed_expressions(store, 5)
    filled, printed = run_fill(store, FakeClaude(fail={ids[2]}), batch=2)
    assert filled == Filled(made=3, skipped=2)
    assert [e.id for e in store.expressions.without_dialogue()] == ids[2:4]
    assert "timed out" in printed


def test_an_unusable_answer_is_skipped_and_left_for_the_next_run(store):
    a, b = seed_expressions(store, 2)
    filled, _ = run_fill(store, FakeClaude(answers={b: []}))
    assert filled == Filled(made=1, skipped=1)
    assert [e.id for e in store.expressions.without_dialogue()] == [b]


def test_only_expressions_without_a_dialogue_are_asked_for_up_to_the_limit(store):
    a, b, c, d = seed_expressions(store, 4)
    store.expressions.set_dialogue(a, [KoreanLine(**line) for line in two_lines(a)])
    claude = FakeClaude()
    run_fill(store, claude, limit=2)
    assert claude.batches == [[b, c]]


def test_nothing_left_asks_claude_nothing(store):
    claude = FakeClaude()
    filled, _ = run_fill(store, claude)
    assert claude.batches == [] and filled == Filled(made=0, skipped=0)
