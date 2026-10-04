"use client";
import { useEffect } from "react";
export default function Accessibility() {
  useEffect(() => {
    let previous: HTMLElement | null = null;
    let active: Element | null = null;
    const focusables = (dialog: Element) =>
      Array.from(
        dialog.querySelectorAll<HTMLElement>(
          'button:not([disabled]),a[href],input:not([disabled]),textarea:not([disabled]),select:not([disabled]),[tabindex="0"]',
        ),
      ).filter((el) => el.offsetParent !== null);
    function observe() {
      const dialogs = document.querySelectorAll('[role="dialog"]');
      const dialog = dialogs[dialogs.length - 1] || null;
      if (dialog !== active) {
        if (dialog) {
          previous = document.activeElement as HTMLElement;
          active = dialog;
          focusables(dialog)[0]?.focus();
        } else {
          active = null;
          previous?.focus();
          previous = null;
        }
      }
    }
    const observer = new MutationObserver(observe);
    observer.observe(document.body, { childList: true, subtree: true });
    function key(e: KeyboardEvent) {
      if (!active) return;
      if (e.key === "Escape") {
        const cancel = Array.from(
          active.querySelectorAll<HTMLButtonElement>("button"),
        ).find(
          (b) =>
            /^(Cancelar|Volver|Cerrar)$/.test(b.textContent?.trim() || "") ||
            b.getAttribute("aria-label") === "Cerrar",
        );
        cancel?.click();
        return;
      }
      if (e.key !== "Tab") return;
      const els = focusables(active);
      if (!els.length) return;
      const first = els[0],
        last = els[els.length - 1];
      if (
        e.shiftKey &&
        (document.activeElement === first ||
          !active.contains(document.activeElement))
      ) {
        e.preventDefault();
        last.focus();
      } else if (
        !e.shiftKey &&
        (document.activeElement === last ||
          !active.contains(document.activeElement))
      ) {
        e.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", key);
    return () => {
      observer.disconnect();
      document.removeEventListener("keydown", key);
    };
  }, []);
  return null;
}
