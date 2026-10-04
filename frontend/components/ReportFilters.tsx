"use client";
import { useEffect, useState } from "react";
import { api, rows, labels, RecordData } from "@/lib/api";
import { Field } from "./ui";
export type ReportFilterValues = Record<string, string>;
export function filterQuery(values: ReportFilterValues) {
  const query = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value)
      query.set(
        key,
        key === "date_from"
          ? `${value}T00:00:00-03:00`
          : key === "date_to"
            ? `${value}T23:59:59.999-03:00`
            : value,
      );
  });
  return query.toString();
}
export default function ReportFilters({
  values,
  onApply,
  onError,
}: {
  values: ReportFilterValues;
  onApply: (values: ReportFilterValues) => void;
  onError: (message: string) => void;
}) {
  const [catalog, setCatalog] = useState<RecordData>({}),
    [clients, setClients] = useState<RecordData[]>([]);
  useEffect(() => {
    let active = true;
    Promise.all([api("/catalog"), api("/clients")])
      .then(([cat, items]) => {
        if (active) {
          setCatalog(cat);
          setClients(rows(items));
        }
      })
      .catch((e) => onError(e.message));
    return () => {
      active = false;
    };
  }, []);
  return (
    <details className="report-filter-panel">
      <summary>
        Filtrar período y cartera
        {Object.values(values).filter(Boolean).length > 0 && (
          <span className="count">
            {Object.values(values).filter(Boolean).length} filtros activos
          </span>
        )}
      </summary>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onApply(
            Object.fromEntries(
              new FormData(e.currentTarget),
            ) as ReportFilterValues,
          );
        }}
      >
        <div className="form-grid">
          <Field
            label="Desde"
            name="date_from"
            type="date"
            value={values.date_from}
          />
          <Field
            label="Hasta"
            name="date_to"
            type="date"
            value={values.date_to}
          />
          <Field
            label="Empresa"
            name="client_id"
            value={values.client_id}
            options={clients.map((c) => ({ value: c.id, label: c.name }))}
          />
          <Field
            label="Estado"
            name="state"
            value={values.state}
            options={[
              "draft",
              "documentation_pending",
              "ready",
              "in_analysis",
              "additional_requested",
              "reanalysis",
              "approved",
              "rejected",
              "cancelled",
            ].map((s) => ({ value: s, label: labels[s] }))}
          />
          <Field
            label="Producto"
            name="product_id"
            value={values.product_id}
            options={rows(catalog.products).map((p) => ({
              value: p.id,
              label: p.name,
            }))}
          />
          <Field
            label="Moneda"
            name="currency"
            value={values.currency}
            options={["USD", "UYU", "EUR"].map((c) => ({ value: c, label: c }))}
          />
          <Field
            label="Gestor comercial"
            name="manager_id"
            value={values.manager_id}
            options={rows(catalog.users).map((u) => ({
              value: u.id,
              label: u.name,
            }))}
          />
          <Field
            label="Analista"
            name="analyst_id"
            value={values.analyst_id}
            options={rows(catalog.users)
              .filter((u) => u.can_analyze)
              .map((u) => ({ value: u.id, label: u.name }))}
          />
          <Field
            label="Perfil documental"
            name="profile_id"
            value={values.profile_id}
            options={rows(catalog.profiles).map((p) => ({
              value: p.id,
              label: p.name,
            }))}
          />
          <Field label="Sucursal" name="branch" value={values.branch} />
          <Field
            label="Actividad económica"
            name="activity"
            value={values.activity}
          />
          <Field
            label="Importe mínimo"
            name="amount_min"
            type="number"
            value={values.amount_min}
          />
          <Field
            label="Importe máximo"
            name="amount_max"
            type="number"
            value={values.amount_max}
          />
        </div>
        <div className="modal-actions">
          <button
            type="button"
            className="secondary"
            onClick={(e) => {
              e.currentTarget.form?.reset();
              onApply({});
            }}
          >
            Limpiar filtros
          </button>
          <button className="primary">Aplicar filtros</button>
        </div>
      </form>
    </details>
  );
}
