"use client";
import { useEffect, useRef } from "react";
const IDLE_LIMIT = 60 * 60 * 1000;
/** Locks sensitive UI using actual interaction, independently of backend session enforcement. */
export function useSessionTimeout(enabled: boolean, onExpire: () => void) {
  const callback = useRef(onExpire);
  callback.current = onExpire;
  useEffect(() => {
    if (!enabled) return;
    let lastActivity = Date.now();
    let timer: ReturnType<typeof setTimeout>;
    let expired = false;
    const expire = () => {
      if (expired) return;
      expired = true;
      callback.current();
    };
    const check = () => {
      const remaining = IDLE_LIMIT - (Date.now() - lastActivity);
      if (remaining <= 0) expire();
      else timer = setTimeout(check, remaining);
    };
    const activity = () => {
      if (expired) return;
      if (Date.now() - lastActivity >= IDLE_LIMIT) {
        expire();
        return;
      }
      lastActivity = Date.now();
      clearTimeout(timer);
      timer = setTimeout(check, IDLE_LIMIT);
    };
    const visible = () => {
      if (document.visibilityState === "visible") {
        clearTimeout(timer);
        check();
      }
    };
    const events = ["pointerdown", "keydown", "touchstart", "wheel"] as const;
    events.forEach((event) =>
      window.addEventListener(event, activity, { passive: true }),
    );
    document.addEventListener("visibilitychange", visible);
    timer = setTimeout(check, IDLE_LIMIT);
    return () => {
      clearTimeout(timer);
      events.forEach((event) => window.removeEventListener(event, activity));
      document.removeEventListener("visibilitychange", visible);
    };
  }, [enabled]);
}
