import { type SyntheticEvent, useRef, useState } from "react";
import { lookUpRegion, outwardCode, PostcodeError, PostcodeLookupError } from "./postcode";

/** A lookup slower than this shows the button as busy, so a quick one does not flash. */
const BUSY_DELAY_MS = 200;

interface PostcodeFormProps {
  readonly onRegion: (regionId: number) => void;
}

/** Asks for a postcode and reports the region NESO places it in. */
export function PostcodeForm({ onRegion }: PostcodeFormProps) {
  const { message, busy, find } = usePostcodeLookup(onRegion);
  const submit = (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    const input = new FormData(event.currentTarget).get("postcode");
    // The lookup reports its own failures to the visitor; anything else is a bug, left to surface as an unhandled rejection.
    void find(typeof input === "string" ? input : "");
  };
  return (
    <form className="postcode-form" onSubmit={submit} noValidate>
      <div className="field">
        <label htmlFor="postcode">Your postcode</label>
        <input
          type="text"
          id="postcode"
          name="postcode"
          placeholder="e.g. BS1"
          autoComplete="postal-code"
          spellCheck={false}
          aria-describedby="postcode-message"
          aria-invalid={message !== ""}
        />
      </div>
      <button className="button button--quiet" type="submit" aria-busy={busy}>
        {busy ? "Finding…" : "Find region"}
      </button>
      <span className="postcode-form__or">or pick a region on the map or from the list</span>
      <p className="field__error" id="postcode-message" role="alert" hidden={message === ""}>
        {message}
      </p>
    </form>
  );
}

/** A newer lookup abandons the one still running, so a slow answer never overrides a later one. */
function usePostcodeLookup(onRegion: (regionId: number) => void) {
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const running = useRef<AbortController | null>(null);

  const find = async (input: string) => {
    // Even a postcode that is rejected abandons the lookup before it, so that one cannot answer over the message.
    running.current?.abort();
    let outward: string;
    try {
      outward = outwardCode(input);
    } catch (error: unknown) {
      if (!(error instanceof PostcodeError)) throw error;
      setMessage(error.message);
      return;
    }
    const lookup = new AbortController();
    running.current = lookup;
    setMessage("");
    const busyTimer = setTimeout(() => {
      setBusy(true);
    }, BUSY_DELAY_MS);
    try {
      onRegion(await lookUpRegion(outward, lookup.signal));
    } catch (error: unknown) {
      if (lookup.signal.aborted) return;
      if (!(error instanceof PostcodeLookupError)) throw error;
      setMessage(error.message);
    } finally {
      clearTimeout(busyTimer);
      if (running.current === lookup) {
        running.current = null;
        setBusy(false);
      }
    }
  };
  return { message, busy, find };
}
