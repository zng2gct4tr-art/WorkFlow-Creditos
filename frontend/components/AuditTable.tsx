"use client";
import { Download } from "lucide-react";
import { RecordData, rows, date } from "@/lib/api";
import { Card, Empty } from "./ui";
export default function AuditTable({ data }: { data: RecordData[] | null }) {
  return (
    <Card
      title="Registro de actividad"
      action={
        <a className="secondary" href="/api/audit/export?format=csv">
          <Download size={15} />
          Exportar CSV
        </a>
      }
    >
      {rows(data).length ? (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Usuario</th>
                <th>Acción</th>
                <th>Recurso</th>
                <th>Identificador</th>
              </tr>
            </thead>
            <tbody>
              {rows(data).map((x) => (
                <tr key={x.id}>
                  <td>{date(x.created_at)}</td>
                  <td>{x.user_name || x.user_id || "Sistema"}</td>
                  <td>{x.action}</td>
                  <td>{x.resource_type || x.resource}</td>
                  <td className="mono">{String(x.resource_id || "—")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty />
      )}
    </Card>
  );
}
