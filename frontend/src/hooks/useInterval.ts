import { useEffect, useRef } from "react";

/**
 * The first polling pattern in this codebase - M1-M4 never needed one,
 * since every job/run there executes synchronously in-request (the
 * frontend just awaits a POST and renders the finished result). M5
 * breaks that: a DeliveryQueueItem moves through
 * queued -> scheduled -> sending -> sent over minutes to days, driven by
 * a worker process with no HTTP request tying it to the browser at the
 * moment it happens - so the campaign detail page needs to actually
 * re-fetch on a timer.
 *
 * Standard "saved callback ref" implementation (the well-known Dan
 * Abramov useInterval pattern) so the interval doesn't need to be torn
 * down and recreated just because the callback closure changed - only
 * `delayMs` changing (or becoming null) restarts/stops it.
 *
 * Pass `delayMs: null` to pause polling entirely - used by
 * DeliveryCampaignDetail to stop once a campaign reaches a terminal
 * status (COMPLETED/CANCELLED), rather than polling forever after
 * there's nothing left to change.
 */
export function useInterval(callback: () => void, delayMs: number | null) {
  const savedCallback = useRef(callback);

  useEffect(() => {
    savedCallback.current = callback;
  }, [callback]);

  useEffect(() => {
    if (delayMs === null) return;
    const id = setInterval(() => savedCallback.current(), delayMs);
    return () => clearInterval(id);
  }, [delayMs]);
}
