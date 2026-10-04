import { Inbox, ChevronRight } from "lucide-react";
import { labels } from "@/lib/api";
export function Badge({ value }: { value: string }) {
  return (
    <span className={`badge ${value}`}>
      {labels[value] || value || "Pendiente"}
    </span>
  );
}
export function Empty({
  title = "Sin registros",
  description = "Los nuevos registros aparecerán aquí.",
}: {
  title?: string;
  description?: string;
}) {
  return (
    <div className="empty">
      <Inbox size={35} />
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}
export function Card({
  title,
  children,
  action,
}: {
  title: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <section className="card">
      <div className="card-heading">
        <h2>{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}
export function Field({
  label,
  name,
  type = "text",
  required = false,
  value,
  options,
}: {
  label: string;
  name: string;
  type?: string;
  required?: boolean;
  value?: any;
  options?: { value: string; label: string }[];
}) {
  return (
    <label className={type === "textarea" ? "field wide" : "field"}>
      <span>
        {label}
        {required ? " *" : ""}
      </span>
      {options ? (
        <select
          aria-label={label}
          name={name}
          defaultValue={value || ""}
          required={required}
        >
          <option value="">Seleccionar</option>
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      ) : type === "textarea" ? (
        <textarea
          aria-label={label}
          name={name}
          defaultValue={value || ""}
          required={required}
          rows={4}
        />
      ) : (
        <input
          aria-label={label}
          name={name}
          type={type}
          defaultValue={value ?? ""}
          required={required}
          step={type === "number" ? "any" : undefined}
        />
      )}
    </label>
  );
}
export function RowAction({ onClick }: { onClick: () => void }) {
  return (
    <button className="icon-button" aria-label="Ver detalle" onClick={onClick}>
      <ChevronRight size={18} />
    </button>
  );
}
