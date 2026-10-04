"use client";
import {
  Files,
  ClipboardCheck,
  Check,
  Clock,
  ArrowUpRight,
  ShieldCheck,
} from "lucide-react";
import { RecordData, labels } from "@/lib/api";
import { Card, Empty } from "./ui";
import OperationalMetrics from "./OperationalMetrics";
export default function Dashboard({
  stats,
  go,
}: {
  stats: RecordData;
  go: (view: string) => void;
}) {
  return (
    <>
      <div className="kpi-grid">
        {[
          [
            "Propuestas activas",
            stats.active_proposals ?? stats.active ?? 0,
            Files,
            "Expedientes en curso",
          ],
          [
            "En análisis",
            stats.in_analysis ?? 0,
            ClipboardCheck,
            "En revisión de Riesgos",
          ],
          [
            "Aprobaciones",
            `${stats.approval_rate ?? 0}%`,
            Check,
            "Sobre propuestas finalizadas",
          ],
          [
            "Fuera de SLA",
            stats.overdue ?? stats.sla_breached ?? 0,
            Clock,
            "Requieren atención",
          ],
        ].map(([title, value, Icon, caption]) => {
          const I = Icon as typeof Files;
          return (
            <div className="kpi" key={String(title)}>
              <div className="kpi-top">
                <span>{String(title)}</span>
                <I size={19} />
              </div>
              <strong>{String(value)}</strong>
              <small>{String(caption)}</small>
            </div>
          );
        })}
      </div>
      <div className="two-columns dashboard-columns">
        <Card
          title="Estado de las propuestas"
          action={
            <button className="text-button" onClick={() => go("proposals")}>
              Ver todas <ArrowUpRight size={15} />
            </button>
          }
        >
          <div className="bar-chart">
            {Object.entries(stats.by_state || stats.states || {}).length ? (
              Object.entries(stats.by_state || stats.states).map(([k, v]) => (
                <div className="bar-row" key={k}>
                  <span>{labels[k] || k}</span>
                  <div>
                    <i
                      style={{
                        width: `${Math.max(3, (Number(v) / (stats.total_proposals || stats.total || 1)) * 100)}%`,
                      }}
                    />
                  </div>
                  <strong>{String(v)}</strong>
                </div>
              ))
            ) : (
              <Empty
                title="Tu operación comienza aquí"
                description="Crea una empresa y su primera propuesta para visualizar resultados reales."
              />
            )}
          </div>
        </Card>
        <Card title="Control documental">
          <div className="document-summary">
            <div className="ring">
              <ShieldCheck size={40} />
            </div>
            <h3>Completitud y validez</h3>
            <p>
              Todos los documentos obligatorios deben estar recibidos y
              validados antes del envío a Riesgos.
            </p>
            <button className="secondary" onClick={() => go("proposals")}>
              Revisar expedientes
              <ArrowUpRight size={15} />
            </button>
          </div>
        </Card>
      </div>
      <OperationalMetrics data={stats} />
      <Card title="Foco operativo">
        <div className="focus-grid">
          <div>
            <span className="focus-icon">
              <Clock />
            </span>
            <strong>SLA comercial</strong>
            <p>7 días hábiles desde la documentación válida hasta el envío.</p>
          </div>
          <div>
            <span className="focus-icon">
              <ClipboardCheck />
            </span>
            <strong>SLA de Riesgos</strong>
            <p>15 días hábiles de análisis, con calendario de Uruguay.</p>
          </div>
          <div>
            <span className="focus-icon">
              <ShieldCheck />
            </span>
            <strong>Trazabilidad integral</strong>
            <p>Cada acción y decisión queda registrada en auditoría.</p>
          </div>
        </div>
      </Card>
    </>
  );
}
