"use client";
import { ArrowLeft, Plus, ArrowUpRight } from "lucide-react";
import { RecordData, rows, money } from "@/lib/api";
import { Card, Badge, Empty } from "./ui";
export default function ClientDetail({
  selected,
  setSelected,
  clientPortal,
  newProposal,
  detail,
}: {
  selected: RecordData;
  setSelected: (value: RecordData | null) => void;
  clientPortal: boolean;
  newProposal: () => Promise<void>;
  detail: (item: RecordData, kind?: string) => Promise<void>;
}) {
  return (
    <>
      <button className="back" onClick={() => setSelected(null)}>
        <ArrowLeft size={16} />
        Volver a clientes
      </button>
      <div className="page-heading">
        <div>
          <span className="eyebrow">CLIENTE EMPRESA</span>
          <h1>{selected.name}</h1>
          <p>
            RUT {selected.rut} ·{" "}
            {selected.activity || "Actividad no registrada"}
          </p>
        </div>
        {!clientPortal && (
          <button className="primary" onClick={newProposal}>
            <Plus size={17} />
            Crear propuesta
          </button>
        )}
      </div>
      <div className="two-columns">
        <Card title="Información de la empresa">
          <dl className="details">
            {[
              ["Cuenta", selected.account_number],
              ["Contacto", selected.contact],
              ["Email", selected.email],
              ["Teléfono", selected.phone],
              ["Dirección", selected.address],
              ["Gestor", selected.manager_name],
            ].map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd>{v || "—"}</dd>
              </div>
            ))}
          </dl>
        </Card>
        <Card title="Resumen financiero">
          <dl className="details">
            {[
              ["Ingresos", selected.financials?.income],
              ["Facturación", selected.financials?.revenue],
              ["EBITDA", selected.financials?.ebitda],
              ["Deuda total", selected.financials?.total_debt],
              ["Deuda con BBVA", selected.financials?.bbva_debt],
            ].map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd>{money(v)}</dd>
              </div>
            ))}
          </dl>
        </Card>
      </div>
      <Card title="Historial de operaciones">
        {rows(selected.proposals).length ? (
          rows(selected.proposals).map((p) => (
            <button className="list-row" key={p.id} onClick={() => detail(p)}>
              <span>{p.code}</span>
              <Badge value={p.state} />
              <span>{money(p.amount, p.currency)}</span>
              <ArrowUpRight size={18} />
            </button>
          ))
        ) : (
          <Empty
            title="Sin operaciones"
            description="Aquí aparecerá el historial de propuestas de esta empresa."
          />
        )}
      </Card>
    </>
  );
}
