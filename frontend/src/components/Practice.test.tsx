import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import type { LiveConnection } from "../lib/liveClient";
import type { LiveEvent } from "../lib/liveSession";
import { SILENCE_MS, type RoundOptions } from "../lib/useLiveRound";
import type { Example, PracticeTarget } from "../types";
import { Practice } from "./Practice";

const connection = {
  microphone: {} as MediaStream,
  finish: vi.fn(),
  say: vi.fn(),
  close: vi.fn(),
  dispose: vi.fn(),
};
let emit: (e: LiveEvent) => void = () => undefined;
const connect = vi.fn(
  async (
    _target: PracticeTarget,
    opts: RoundOptions,
  ): Promise<LiveConnection> => {
    emit = opts.onEvent;
    return connection;
  },
);

vi.mock("../lib/liveClient", () => ({
  connectExample: (target: PracticeTarget, opts: RoundOptions) =>
    connect(target, opts),
}));
vi.mock("../api", () => ({
  api: { addExample: vi.fn(), exampleFeedback: vi.fn() },
}));

const target: PracticeTarget = {
  text: "read too much into something",
  meaning: "to find a meaning that probably is not there",
  note: "takes 'into', not 'in'",
};

const kept: Example = {
  id: 7,
  created_at: "",
  session_id: 3,
  expression: target.text,
  user_text: "Don't read too much in his silence.",
  coach_text: "Don't read too much into his silence. It's 'into', not 'in'.",
  seconds: 14,
};

function renderPractice(examples: Example[] = [], onKept = vi.fn()) {
  render(
    <Practice
      target={target}
      label="Your turn: one sentence each."
      sessionId={3}
      examples={examples}
      onKept={onKept}
    />,
  );
  return onKept;
}

const feedback = {
  paraphrase: "Don't read too much into his silence.",
  feedback: "It's 'into', not 'in'.",
};

beforeEach(() => {
  connect.mockClear();
  connection.dispose.mockClear();
  connection.say.mockClear();
  connection.close.mockClear();
  vi.mocked(api.addExample).mockReset().mockResolvedValue(kept);
  vi.mocked(api.exampleFeedback).mockReset().mockResolvedValue(feedback);
});

/** The reader says the sentence; the coach signals it heard it; the native version comes back and is read aloud. */
async function sayAndHear() {
  await userEvent.click(screen.getByRole("button", { name: /Your turn/ }));
  act(() => emit({ type: "session.started", session: { id: "live_1" } }));
  act(() =>
    emit({
      type: "session.input_transcript.delta",
      delta: "Don't read too much in his silence.",
    }),
  );
  act(() =>
    emit({ type: "session.output_transcript.delta", delta: "Got it." }),
  );
  await screen.findByText("It's 'into', not 'in'.");
  act(() =>
    emit({
      type: "session.output_transcript.delta",
      delta: " Don't read too much into his silence. It's 'into', not 'in'.",
    }),
  );
  act(() => emit({ type: "session.usage.updated", usage: { seconds: 14 } }));
  await userEvent.click(screen.getByRole("button", { name: "Done" }));
  act(() => emit({ type: "session.closed", usage: { seconds: 14 } }));
}

describe("Practice", () => {
  it("opens a round on the target and stacks the kept sentence under it", async () => {
    const onKept = renderPractice();
    await sayAndHear();
    expect(connect.mock.calls[0][0]).toBe(target);

    await userEvent.click(screen.getByRole("button", { name: "Keep" }));
    expect(vi.mocked(api.addExample)).toHaveBeenCalledWith({
      session_id: 3,
      expression: target.text,
      user_text: "Don't read too much in his silence.",
      coach_text:
        "Don't read too much into his silence. It's 'into', not 'in'.",
      seconds: 14,
    });
    expect(onKept).toHaveBeenCalledWith(kept);
    // The slip closes so the next sentence can start from the label.
    expect(
      screen.getByRole("button", { name: /Your turn/ }),
    ).toBeInTheDocument();
  });

  it("asks the text coach once the sentence is in, and has the answer read aloud", async () => {
    renderPractice();
    await sayAndHear();
    expect(vi.mocked(api.exampleFeedback)).toHaveBeenCalledWith(
      target,
      "Don't read too much in his silence.",
    );
    expect(connection.say).toHaveBeenCalledWith(
      "Don't read too much into his silence. It's 'into', not 'in'.",
    );
    // The Coach line is the written answer, never the live transcript's "Got it."
    expect(screen.queryByText(/Got it/)).not.toBeInTheDocument();
    expect(
      screen.getByText("Don't read too much into his silence."),
    ).toBeInTheDocument();
  });

  it("holds the round open while the answer is being written", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let answer: (f: typeof feedback) => void = () => undefined;
    vi.mocked(api.exampleFeedback).mockReturnValue(
      new Promise((resolve) => (answer = resolve)),
    );
    renderPractice();
    await userEvent.click(screen.getByRole("button", { name: /Your turn/ }));
    act(() => emit({ type: "session.started", session: { id: "live_1" } }));
    act(() =>
      emit({ type: "session.input_transcript.delta", delta: "A sentence." }),
    );
    act(() =>
      emit({ type: "session.output_transcript.delta", delta: "Got it." }),
    );
    expect(screen.getByText("Writing the native version…")).toBeInTheDocument();

    await act(async () => {
      vi.advanceTimersByTime(SILENCE_MS + 1000);
    });
    expect(connection.close).not.toHaveBeenCalled();

    await act(async () => answer(feedback));
    await act(async () => {
      vi.advanceTimersByTime(SILENCE_MS + 1000);
    });
    expect(connection.close).toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("shows why when the answer does not come, and keeps nothing", async () => {
    vi.mocked(api.exampleFeedback).mockRejectedValue(
      new Error("feedback failed: claude timed out after 90s"),
    );
    renderPractice();
    await userEvent.click(screen.getByRole("button", { name: /Your turn/ }));
    act(() => emit({ type: "session.started", session: { id: "live_1" } }));
    act(() =>
      emit({ type: "session.input_transcript.delta", delta: "A sentence." }),
    );
    act(() =>
      emit({ type: "session.output_transcript.delta", delta: "Got it." }),
    );
    expect(await screen.findByText(/claude timed out/)).toBeInTheDocument();
    act(() => emit({ type: "session.closed" }));
    expect(screen.getByRole("button", { name: "Keep" })).toBeDisabled();
  });

  it("shows earlier sentences with the coach line under each, oldest first", () => {
    const older = {
      ...kept,
      id: 6,
      user_text: "First try.",
      coach_text: "First try. Natural.",
    };
    renderPractice([older, kept]);
    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("First try.");
    expect(items[0]).toHaveTextContent("First try. Natural.");
    expect(items[1]).toHaveTextContent("It's 'into', not 'in'.");
  });

  it("discards with ✕ while still listening, dropping the connection", async () => {
    const onKept = renderPractice();
    await userEvent.click(screen.getByRole("button", { name: /Your turn/ }));
    act(() => emit({ type: "session.started", session: { id: "live_1" } }));
    act(() =>
      emit({ type: "session.input_transcript.delta", delta: "hello?" }),
    );

    await userEvent.click(screen.getByRole("button", { name: "Discard" }));
    expect(connection.dispose).toHaveBeenCalled();
    expect(onKept).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: /Your turn/ }),
    ).toBeInTheDocument();
  });

  it("retries with ↻, both mid-round and after, starting a fresh round each time", async () => {
    renderPractice();
    await userEvent.click(screen.getByRole("button", { name: /Your turn/ }));
    act(() => emit({ type: "session.started", session: { id: "live_1" } }));
    act(() =>
      emit({ type: "session.input_transcript.delta", delta: "wrong start" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(connect).toHaveBeenCalledTimes(2);
    expect(screen.queryByText("wrong start")).not.toBeInTheDocument();

    act(() => emit({ type: "session.started", session: { id: "live_2" } }));
    await userEvent.click(screen.getByRole("button", { name: "Done" }));
    act(() => emit({ type: "session.closed" }));
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(connect).toHaveBeenCalledTimes(3);
  });

  it("will not keep a round the coach never answered", async () => {
    renderPractice();
    await userEvent.click(screen.getByRole("button", { name: /Your turn/ }));
    act(() => emit({ type: "session.started", session: { id: "live_1" } }));
    act(() =>
      emit({ type: "session.input_transcript.delta", delta: "hello?" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Done" }));
    act(() => emit({ type: "session.closed" }));
    expect(screen.getByRole("button", { name: "Keep" })).toBeDisabled();
  });

  it("keeps the slip up with the error when the write fails", async () => {
    vi.mocked(api.addExample).mockRejectedValueOnce(
      new Error("database is locked"),
    );
    renderPractice();
    await sayAndHear();
    await userEvent.click(screen.getByRole("button", { name: "Keep" }));
    expect(await screen.findByText(/database is locked/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Keep" })).toBeInTheDocument();
  });
});
