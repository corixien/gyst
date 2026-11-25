import { browser } from 'wxt/browser';

// Native messaging host of the Linux companion (companion/). Without it nothing is free and no windows can be edited.
export const COMPANION = 'gyst_companion';

export interface FreeWindow {
  from: string; // "HH:MM" local time
  to: string; // "HH:MM" local time, may be earlier than from (wraps midnight)
}

export interface CompanionReply {
  free?: boolean;
  ok?: boolean;
  config?: { free_windows: FreeWindow[] };
}

// Resolves null when the companion is missing, not running or answers with an error.
export const askCompanion = (message: Record<string, unknown>): Promise<CompanionReply | null> =>
  browser.runtime.sendNativeMessage(COMPANION, message).then(
    (reply: CompanionReply & { error?: string }) => (reply && !reply.error ? reply : null),
    () => null,
  );
