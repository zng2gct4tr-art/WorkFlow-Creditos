"use client";
import { Search } from "lucide-react";
import { RecordData, labels, money, date } from "@/lib/api";
import { Card, Empty, Badge, RowAction } from "./ui";
export default function RecordsList({
  view,
  filtered,
  query,
  setQuery,
  status,
  setStatus,
  detail,
}: {
  view: string;
  filtered: RecordData[];
  query: string;
  setQuery: (value: string) => void;
  status: string;
  setStatus: (value: string) => void;
  detail: (item: RecordData, kind?: string) => Promise<void>;
}) {
  return (
    <Card
      title={
        view === "clients"
          ? "Cartera de empresas"
          : view === "analysis"
            ? "Expedientes para revisión"
            : "Todas las propuestas"
      }
      action={<span className="count">{filtered.length} registros</span>}
    >
      <div className="table-toolbar">
        <label className="search">
          <Search size={17} />
          <input
            placeholder={
              view === "clients"
                ? "Buscar por empresa, RUT o cuenta"
                : "Buscar por expediente o empresa"
            }
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        {view !== "clients" && (
          <select
            aria-label="Filtrar por estado"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="">Todos los estados</option>
            {Object.entries(labels)
              .slice(0, 9)
              .map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
          </select>
        )}
      </div>
      {filtered.length ? (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                {(view === "clients"
                  ? ["Empresa / RUT", "Contacto", "Actividad", "Gestor", ""]
                  : [
                      "Expediente / Empresa",
                      "Producto",
                      "Importe",
                      "Estado",
                      "Creada",
                      "",
                    ]
                ).map((c, i) => (
                  <th key={i}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={r.id}>
                  {view === "clients" ? (
                    <>
                      <td>
                        <strong>{r.name}</strong>
                        <small>{r.rut}</small>
                      </td>
                      <td>{r.contact || r.email || "—"}</td>
                      <td>{r.activity || "—"}</td>
                      <td>{r.manager_name || "—"}</td>
                    </>
                  ) : (
                    <>
                      <td>
                        <strong>{r.code}</strong>
                        <small>{r.client_name}</small>
                      </td>
                      <td>{r.product_name || "—"}</td>
                      <td className="amount">{money(r.amount, r.currency)}</td>
                      <td>
                        <Badge value={r.state} />
                      </td>
                      <td>{date(r.created_at)}</td>
                    </>
                  )}
                  <td>
                    <RowAction
                      onClick={() =>
                        detail(r, view === "clients" ? "client" : "proposal")
                      }
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty
          title={
            query || status
              ? "No encontramos resultados"
              : "Todavía no hay registros"
          }
          description={
            query || status
              ? "Prueba con otros filtros de búsqueda."
              : "Los registros creados y autorizados para tu cuenta aparecerán aquí."
          }
        />
      )}
    </Card>
  );
}
