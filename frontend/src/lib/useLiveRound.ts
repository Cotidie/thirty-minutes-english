import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type RefObject,
} from "react";
import type { LiveConnection, LiveOptions } from "./liveClient";
import {
  applyLiveEvent,
  initialLiveState,
  liveFailed,
  type LiveState,
} from "./liveSession";

export type RoundOptions = Omit<LiveOptions, "start">;
export type Connect = (opts: RoundOptions) => Promise<LiveConnection>;
export type Keep = (round: LiveState) => Promise<void>;
/**
 * Runs once per round, when the coach first speaks (the sentence is in). The
 * round stays open until it settles; `say` has the coach read text aloud.
 */
export type OnTurn = (
  round: LiveState,
  say: (text: string) => void,
) => Promise<void>;

/** How long the coach stays quiet before we take the round as finished. */
export const SILENCE_MS = 5000;

export interface LiveRound {
  state: LiveState | null;
  saved: boolean;
  microphone: MediaStream | null;
  /** Opens a round. Also the retry: drops whatever was said and opens a fresh one. */
  start(): Promise<void>;
  /** Ends the round; the transcript stays up until saved or dismissed. */
  close(): void;
  /** Drops the round and its transcript. */
  dismiss(): void;
  /** Hands the transcript to `keep`. Resolves true once it is written. */
  save(): Promise<boolean>;
}

/**
 * One GPT-Live round behind a button: open, listen, close on its own once the
 * coach has been quiet, then wait to be told whether to keep the transcript.
 * The component owns the <audio> element the coach's voice plays through.
 */
export function useLiveRound(
  audio: RefObject<HTMLAudioElement | null>,
  connect: Connect,
  keep: Keep,
  onTurn?: OnTurn,
): LiveRound {
  const [state, setState] = useState<LiveState | null>(null);
  const [saved, setSaved] = useState(false);
  const [microphone, setMicrophone] = useState<MediaStream | null>(null);
  const connRef = useRef<LiveConnection | null>(null);
  const latest = useRef<LiveState | null>(null);
  const silence = useRef<ReturnType<typeof setTimeout> | null>(null);
  // The turn hand-off: not yet taken, taken and still being answered, or done.
  const turn = useRef<"open" | "pending" | "done">("open");
  const handlers = useRef({ connect, keep, onTurn });

  // Handlers close over props that change; the round always calls the newest.
  useEffect(() => {
    handlers.current = { connect, keep, onTurn };
  });

  const apply = (change: (s: LiveState) => LiveState) => {
    latest.current = change(latest.current ?? initialLiveState);
    setState(latest.current);
  };

  const clearSilence = () => {
    if (silence.current) clearTimeout(silence.current);
    silence.current = null;
  };

  useEffect(
    () => () => {
      clearSilence();
      connRef.current?.dispose();
    },
    [],
  );

  const save = useCallback(async () => {
    const round = latest.current;
    if (!round) return false;
    setSaved(true);
    try {
      await handlers.current.keep(round);
      return true;
    } catch (e) {
      setSaved(false);
      apply((s) => ({
        ...s,
        error: e instanceof Error ? e.message : String(e),
      }));
      return false;
    }
  }, []);

  const close = useCallback(() => {
    clearSilence();
    setMicrophone(null);
    apply((s) => ({ ...s, status: "closing" }));
    connRef.current?.close();
  }, []);

  const armSilence = useCallback(() => {
    clearSilence();
    silence.current = setTimeout(close, SILENCE_MS);
  }, [close]);

  /** The coach has started answering: hand the round over once, and hold it open until the answer is in. */
  const takeTurn = useCallback(
    (round: LiveState) => {
      const { onTurn } = handlers.current;
      if (!onTurn) return armSilence();
      turn.current = "pending";
      onTurn(round, (text) => connRef.current?.say(text))
        .catch((e: unknown) =>
          apply((s) => ({
            ...s,
            error: e instanceof Error ? e.message : String(e),
          })),
        )
        .finally(() => {
          if (turn.current !== "pending") return;
          turn.current = "done";
          armSilence();
        });
    },
    [armSilence],
  );

  const start = useCallback(async () => {
    clearSilence();
    connRef.current?.dispose();
    connRef.current = null;
    setMicrophone(null);
    turn.current = "open";
    latest.current = initialLiveState;
    setState(initialLiveState);
    setSaved(false);
    try {
      const conn = await handlers.current.connect({
        audio: audio.current!,
        onEvent: (event) => {
          apply((s) => applyLiveEvent(s, event));
          if (event.type !== "session.output_transcript.delta") return;
          if (turn.current === "open") takeTurn(latest.current!);
          else if (turn.current === "done") armSilence();
        },
        onDisconnect: () => {
          setMicrophone(null);
          apply((s) => liveFailed(s, "Connection dropped."));
        },
      });
      connRef.current = conn;
      setMicrophone(conn.microphone);
    } catch (e) {
      apply((s) => liveFailed(s, e instanceof Error ? e.message : String(e)));
    }
  }, [audio, armSilence, takeTurn]);

  const dismiss = useCallback(() => {
    clearSilence();
    connRef.current?.dispose();
    connRef.current = null;
    setMicrophone(null);
    turn.current = "open";
    latest.current = null;
    setState(null);
  }, []);

  return { state, saved, microphone, start, close, dismiss, save };
}

/** A round with nothing on one of the two lines has nothing to keep. */
export function hasBothLines(state: LiveState): boolean {
  return state.user.trim() !== "" && state.coach.trim() !== "";
}
