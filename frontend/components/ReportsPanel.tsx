"use client";
import { Download, ArrowUpRight } from "lucide-react";
import { RecordData } from "@/lib/api";
import { Card } from "./ui";
import OperationalMetrics from "./OperationalMetrics";
import { filterQuery, ReportFilterValues } from "./ReportFilters";
export default function ReportsPanel({
  data,
  reportFilters,
}: {
  data: RecordData | null;
  reportFilters: ReportFilterValues;
}) {
  return (
    <>
      <Card title="Exportar reporte de operación">
        <p className="card-description">
          Descarga la información autorizada de tu cartera con indicadores de
          productividad, estados y cumplimiento de SLA.
        </p>
        <div className="export-grid">
          {["csv", "xlsx", "pdf"].map((f) => (
            <a
              key={f}
              className="export-card"
              href={`/api/reports/export?format=${f}&${filterQuery(reportFilters)}`}
            >
              <Download size={24} />
              <strong>{f.toUpperCase()}</strong>
              <span>Descargar reporte</span>
              <ArrowUpRight size={18} />
            </a>
          ))}
        </div>
      </Card>
      <OperationalMetrics data={data || {}} />
      <Card title="Indicadores del período">
        <dl className="details">
          {Object.entries(data || {})
            .filter(([, v]) => typeof v !== "object")
            .map(([k, v]) => (
              <div key={k}>
                <dt>
                  {(
                    {
                      approval_rate: "Porcentaje de aprobación",
                      active_proposals: "Propuestas activas",
                      in_analysis: "En análisis",
                      overdue: "SLA vencido",
                      total_proposals: "Total de propuestas",
                      upcoming: "Próximas a vencer",
                      approved_with_incidents: "Aprobadas con incidencias",
                      approved_without_incidents: "Aprobadas sin incidencias",
                      report_quality_source: "Origen de calidad del informe",
                      avg_automatic_report_quality:
                        "Calidad automática media del informe",
                      rejection_rate: "Porcentaje de rechazo",
                      document_completeness: "Completitud documental media",
                      document_incidents: "Incidencias documentales",
                      avg_report_quality: "Calidad media del informe",
                      avg_commercial_days: "Tiempo comercial medio (días)",
                      avg_risk_days: "Tiempo medio de Riesgos (días)",
                      avg_total_days: "Tiempo total medio (días)",
                      commercial_breached_pct: "Comercial fuera de SLA (%)",
                      risk_breached_pct: "Riesgos fuera de SLA (%)",
                    } as any
                  )[k] || k}
                </dt>
                <dd>
                  {k === "report_quality_source"
                    ? v === "human"
                      ? "Evaluación humana"
                      : "Evaluación automática"
                    : String(v)}
                </dd>
              </div>
            ))}
        </dl>
      </Card>
    </>
  );
}
