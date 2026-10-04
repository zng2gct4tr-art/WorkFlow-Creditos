import { RecordData, rows } from "@/lib/api";
import { Card, Empty } from "./ui";
export default function OperationalMetrics({ data }: { data: RecordData }) {
  const value = (v: any, suffix = "") =>
    v === null || v === undefined ? "Sin medición" : `${v}${suffix}`;
  return (
    <>
      <div className="kpi-grid operational-metrics">
        {[
          ["Calidad del informe · humana", data.avg_report_quality, " / 100"],
          [
            "Calidad del informe · automática",
            data.avg_automatic_report_quality ?? data.avg_ai_report_quality,
            " / 100",
          ],
          ["Tiempo comercial medio", data.avg_commercial_days, " días"],
          ["Tiempo medio de Riesgos", data.avg_risk_days, " días"],
          ["Tiempo total medio", data.avg_total_days, " días"],
          ["Comercial fuera de SLA", data.commercial_breached_pct, "%"],
          ["Riesgos fuera de SLA", data.risk_breached_pct, "%"],
          ["Documentos con incidencias", data.document_incidents, ""],
        ].map(([label, metric, suffix]) => (
          <div className="kpi" key={label}>
            <div className="kpi-top">{label}</div>
            <strong>
              {label.includes("Calidad") && metric == null
                ? "Sin evaluación"
                : value(metric, suffix)}
            </strong>
          </div>
        ))}
      </div>
      <Card title="Evolución de propuestas por mes">
        {rows(data.trend).length ? (
          <div
            className="trend-chart"
            role="img"
            aria-label={rows(data.trend)
              .map((t) => `${t.period}: ${t.total} propuestas`)
              .join("; ")}
          >
            {rows(data.trend).map((t) => (
              <div className="trend-column" key={t.period}>
                <span>{t.total}</span>
                <div className="trend-bar-container">
                  <i
                    style={{
                      height: `${Math.max(5, (t.total / Math.max(...rows(data.trend).map((x) => x.total), 1)) * 100)}%`,
                    }}
                  />
                </div>
                <small>{t.period}</small>
              </div>
            ))}
          </div>
        ) : (
          <Empty
            title="Sin evolución disponible"
            description="La tendencia mensual aparecerá cuando existan propuestas en el período seleccionado."
          />
        )}
      </Card>
      <div className="two-columns">
        {[
          ["by_manager", "Resultados por gestor comercial"],
          ["by_analyst", "Resultados por analista"],
        ].map(([key, title]) => (
          <Card title={title} key={key}>
            {rows(data[key]).length ? (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Integrante</th>
                      <th>Propuestas</th>
                      <th>Aprobadas</th>
                      <th>Rechazadas</th>
                      <th>En curso</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows(data[key]).map((person) => (
                      <tr key={person.user_id}>
                        <td>
                          <strong>{person.name}</strong>
                        </td>
                        <td>{person.total}</td>
                        <td>{person.states?.approved || 0}</td>
                        <td>{person.states?.rejected || 0}</td>
                        <td>
                          {person.total -
                            (person.states?.approved || 0) -
                            (person.states?.rejected || 0) -
                            (person.states?.cancelled || 0)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty title="Sin resultados en este período" />
            )}
          </Card>
        ))}
      </div>
    </>
  );
}
