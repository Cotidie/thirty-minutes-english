"""Fills the corpus expressions that have no Korean dialogue yet, a batch at a time, with Claude. Run on the server:

    docker compose exec backend uv run --no-dev python -m app.generation.korean_dialogues [--apply] [--limit N]

Without --apply it only prints what Claude wrote. With it, each batch is saved as it comes back, so a run that stops
halfway keeps what it finished, and running again asks only for the expressions still without one.
"""

import argparse
import json
import logging
import os
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TextIO

from app.db import Database
from app.db.expressions import ExpressionRepo
from app.llm import Claude, GenerationError, Runner
from app.main import ROOT
from app.models import Expression, KoreanLine

BATCH = 20
MODEL = "opus"
EFFORT = "medium"
TIMEOUT_S = 300

PROMPT = """You write short Korean dialogues for two Korean learners of English who practise together. For each
expression below, write a two-line dialogue: A says one line, then B answers or reacts to it. Each learner says one
line in English, then checks the model answer.

- At least one line's English says the expression. The other line may leave it out when the dialogue sounds more
  natural that way. Never force it into both lines.
- Decide from the dialogue whether A's or B's line carries the expression. Across the batch, do not always put it on
  the same side.
- Set the dialogue in a different situation from the expression's English examples and from its Korean example.
- The Korean is everyday spoken Korean, the way people actually talk. The English is a natural rendering of that
  Korean, and the line with the expression uses it with its meaning and as its usage note describes.
- Keep each line short: one or two sentences.

Give one entry in `dialogues` for every id below, with its two lines in order, A first.

Expressions:
"""

LINE = {
    "type": "object",
    "properties": {"korean": {"type": "string", "minLength": 1}, "english": {"type": "string", "minLength": 1}},
    "required": ["korean", "english"],
}
SCHEMA = {
    "type": "object",
    "properties": {
        "dialogues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "lines": {"type": "array", "minItems": 2, "maxItems": 2, "items": LINE},
                },
                "required": ["id", "lines"],
            },
        }
    },
    "required": ["dialogues"],
}


def prompt_for(expressions: list[Expression]) -> str:
    """The instructions, then each expression as the JSON Claude reads."""
    return PROMPT + json.dumps([_brief(e) for e in expressions], ensure_ascii=False, indent=2)


def _brief(expression: Expression) -> dict:
    example = expression.korean_example
    return {
        "id": expression.id,
        "phrase": expression.phrase,
        "meaning": expression.meaning,
        "usage_note": expression.usage_note,
        "examples": expression.examples,
        "korean_example": example and example.model_dump(),
    }


class DialogueWriter:
    """One batch of expressions in, the usable dialogues out, by expression id."""

    def __init__(self, runner: Runner) -> None:
        self._runner = runner

    def write(self, expressions: list[Expression]) -> dict[int, list[KoreanLine]]:
        """Only the first answer for each id that was asked for, and only when it has two lines with text in each.
        Raises GenerationError when Claude fails."""
        answer = self._runner.run(prompt_for(expressions), SCHEMA)
        asked = {e.id for e in expressions}
        written: dict[int, list[KoreanLine]] = {}
        for dialogue in answer.get("dialogues", []):
            expression_id, lines = dialogue.get("id"), dialogue.get("lines")
            if expression_id in asked and expression_id not in written and _usable(lines):
                written[expression_id] = [KoreanLine(korean=line["korean"], english=line["english"]) for line in lines]
        return written


def _usable(lines: object) -> bool:
    return (
        isinstance(lines, list)
        and len(lines) == 2
        and all(
            isinstance(line, dict) and all(isinstance(line.get(k), str) and line[k].strip() for k in ("korean", "english"))
            for line in lines
        )
    )


@dataclass(frozen=True)
class Filled:
    """How many expressions got a dialogue (written, or only printed in a preview) and how many are still without."""

    made: int
    skipped: int


def fill(expressions: ExpressionRepo, writer: DialogueWriter, *, limit: int | None, batch: int, apply: bool, out: TextIO) -> Filled:
    """Asks for a dialogue for each expression that has none, `batch` at a time, prints each, and saves it with `apply`."""
    made = skipped = 0
    for chunk in _chunks(expressions.without_dialogue(limit), batch):
        try:
            dialogues = writer.write(chunk)
        except GenerationError as e:
            _warn(out, chunk, str(e))
            skipped += len(chunk)
            continue
        _show(out, chunk, dialogues)
        if apply:
            _save(expressions, dialogues)
        made += len(dialogues)
        skipped += len(chunk) - len(dialogues)
    filled = Filled(made, skipped)
    _summarize(out, filled, apply)
    return filled


def _chunks(items: list[Expression], size: int) -> Iterator[list[Expression]]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _show(out: TextIO, chunk: list[Expression], dialogues: dict[int, list[KoreanLine]]) -> None:
    for expression in chunk:
        lines = dialogues.get(expression.id)
        if lines is None:
            _warn(out, [expression], "no usable dialogue came back")
            continue
        print(f"#{expression.id} {expression.phrase}", file=out)
        for speaker, line in zip("AB", lines):
            print(f"  {speaker}  {line.korean}\n     {line.english}", file=out)


def _warn(out: TextIO, chunk: list[Expression], reason: str) -> None:
    ids = ", ".join(f"#{e.id}" for e in chunk)
    print(f"skipped {ids}: {reason}", file=out)


def _save(expressions: ExpressionRepo, dialogues: dict[int, list[KoreanLine]]) -> None:
    for expression_id, lines in dialogues.items():
        expressions.set_dialogue(expression_id, lines)


def _summarize(out: TextIO, filled: Filled, apply: bool) -> None:
    if apply:
        print(f"wrote {filled.made}, skipped {filled.skipped}", file=out)
    else:
        print(f"made {filled.made}, skipped {filled.skipped} (preview, nothing written)", file=out)


def main(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    db = Database(os.environ.get("DB_PATH", ROOT / "data" / "sessions.db"))
    writer = DialogueWriter(Claude(args.model, args.effort, TIMEOUT_S))
    filled = fill(db.expressions, writer, limit=args.limit, batch=args.batch, apply=args.apply, out=sys.stdout)
    return 1 if filled.skipped else 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.generation.korean_dialogues",
        description="Fills the corpus expressions that have no Korean dialogue yet, a batch at a time, with Claude.",
    )
    parser.add_argument("--apply", action="store_true", help="save the dialogues; without it, only print them")
    parser.add_argument("--limit", type=_positive, help="ask for at most this many expressions")
    parser.add_argument("--batch", type=_positive, default=BATCH, help=f"expressions per Claude run (default {BATCH})")
    parser.add_argument("--model", default=MODEL, help=f"Claude model (default {MODEL})")
    parser.add_argument("--effort", default=EFFORT, help=f"effort level (default {EFFORT})")
    return parser


def _positive(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be 1 or more, not {value}")
    return value


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
