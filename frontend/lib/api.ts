export type RecordData = Record<string, any>;
export async function api(path: string, options: RequestInit = {}) {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  const csrf =
    typeof document === "undefined"
      ? ""
      : document.cookie
          .split("; ")
          .find((x) => x.startsWith("wf_csrf="))
          ?.split("=")
          .slice(1)
          .join("=");
  if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  const response = await fetch("/api" + path, {
    ...options,
    headers,
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) {
    if (
      response.status === 401 &&
      path !== "/auth/login" &&
      typeof window !== "undefined"
    )
      window.dispatchEvent(new Event("wf-session-expired"));
    let detail;
    try {
      detail = (await response.json()).detail;
    } catch {}
    const fieldNames: Record<string, string> = {
      rut: "RUT (12 dígitos)",
      account_number: "Número de cuenta",
      password: "Contraseña (mínimo 12 caracteres)",
      name: "Razón social o nombre",
      profile_id: "Perfil documental",
      manager_id: "Gestor comercial",
      amount: "Importe",
      term_months: "Plazo",
      purpose: "Finalidad",
      email: "Correo electrónico",
    };
    if (Array.isArray(detail))
      throw new Error(
        "Revisa los siguientes campos: " +
          detail
            .map(
              (d: any) =>
                fieldNames[d.loc?.at(-1)] ||
                d.loc?.at(-1) ||
                "Datos de la solicitud",
            )
            .join(", ") +
          ".",
      );
    throw new Error(
      typeof detail === "string"
        ? detail
        : detail?.message
          ? detail.message
          : response.status === 401
            ? "Tu sesión finalizó. Inicia sesión nuevamente."
            : response.status === 403
              ? "No tienes permiso para realizar esta acción."
              : "No se pudo completar la operación. Revisa los datos e inténtalo nuevamente.",
    );
  }
  if (response.status === 204) return null;
  return response.json();
}
export const rows = (data: any): RecordData[] =>
  Array.isArray(data) ? data : data?.items || data?.results || [];
/** Formats decimal strings without converting monetary values to floating point. */
export const money = (value: unknown, currency = "USD") => {
  if (value === undefined || value === null || value === "") return "—";
  const parsed = String(value)
    .trim()
    .match(/^(-?)(\d+)(?:\.(\d+))?$/);
  if (!parsed) return "—";
  const fraction = (parsed[3] || "").padEnd(2, "0");
  let cents = BigInt(parsed[2]) * BigInt(100) + BigInt(fraction.slice(0, 2));
  if (fraction.length > 2 && fraction[2] >= "5") cents += BigInt(1);
  const units = cents / BigInt(100),
    decimal = String(cents % BigInt(100)).padStart(2, "0"),
    negative = parsed[1] === "-" && cents > BigInt(0);
  try {
    const formatter = new Intl.NumberFormat("es-UY", {
      style: "currency",
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
    const parts = formatter.formatToParts(
      negative && units === BigInt(0) ? -BigInt(1) : negative ? -units : units,
    );
    return parts
      .map((part) =>
        part.type === "fraction"
          ? decimal
          : negative && units === BigInt(0) && part.type === "integer"
            ? "0"
            : part.value,
      )
      .join("");
  } catch {
    return "—";
  }
};
export const date = (value: any) =>
  value
    ? new Intl.DateTimeFormat("es-UY", {
        timeZone: "America/Montevideo",
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(value))
    : "—";
export const labels: Record<string, string> = {
  draft: "Borrador",
  documentation_pending: "Documentación pendiente",
  ready: "Lista para enviar",
  in_analysis: "En análisis",
  additional_requested: "Información adicional",
  reanalysis: "En análisis nuevamente",
  correct: "Correcto",
  incorrect: "Incorrecto",
  green: "Dentro del SLA",
  yellow: "Próximo a vencer",
  red: "SLA vencido",
  paused: "SLA pausado",
  validating: "En validación",
  approved: "Aprobada",
  rejected: "Rechazada",
  cancelled: "Cancelada",
  pending: "Pendiente",
  uploaded: "Cargado",
  processing: "En validación",
  valid: "Correcto",
  invalid: "Incorrecto",
  expired: "Vencido",
};
