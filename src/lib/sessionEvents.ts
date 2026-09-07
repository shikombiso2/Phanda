/**
 * Broadcasts "this session is over, go to login" -- exactly once per dead
 * session, no matter how many requests were queued behind the refresh that
 * killed it.
 *
 * Without the guard, four screens each holding a stale access token would
 * each hit 401, each await the one shared refresh (see api.ts), each see it
 * fail, and each independently redirect to login -- fine in effect, but a
 * flicker of stacked navigations. The boolean below collapses that to one.
 * A plain boolean is enough: JavaScript has no preemptive threading, so
 * there is no window between checking it and setting it where two callers
 * could both pass.
 */
let alreadySignalled = false;
let listener: (() => void) | null = null;

export function onSessionExpired(fn: () => void): void {
  listener = fn;
}

export function signalSessionExpired(): void {
  if (alreadySignalled) return;
  alreadySignalled = true;
  listener?.();
}

/** Called after a successful login/register so a future expiry can signal again. */
export function resetSessionExpiry(): void {
  alreadySignalled = false;
}
