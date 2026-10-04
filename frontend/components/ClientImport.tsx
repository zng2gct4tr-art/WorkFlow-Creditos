"use client";
import { useState } from "react";
import { Upload, Download } from "lucide-react";
import { api, RecordData } from "@/lib/api";
import { Card } from "./ui";
export default function ClientImport({
  onDone,
  onError,
}: {
  onDone: () => void;
  onError: (s: string) => void;
}) {
  const [file, setFile] = useState<File | null>(null),
    [result, setResult] = useState<RecordData | null>(null),
    [busy, setBusy] = useState(false);
  async function send(commit = false) {
    if (!file) return;
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("commit", String(commit));
      const r = await api("/import/clients", { method: "POST", body: form });
      setResult(r);
      if (commit) onDone();
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card
      title="Importar empresas"
      action={
        <a className="secondary" href="/api/import/template">
          <Download size={15} />
          Plantilla CSV
        </a>
      }
    >
      <p className="card-description">
        Carga un archivo CSV o Excel. Revisa todas las filas antes de incorporar
        las empresas a tu cartera.
      </p>
      <div className="import-controls">
        <label className="field">
          <span>Archivo de empresas</span>
          <input
            type="file"
            accept=".csv,.xlsx"
            onChange={(e) => {
              setFile(e.target.files?.[0] || null);
              setResult(null);
            }}
          />
        </label>
        <button
          className="secondary"
          disabled={busy || !file}
          onClick={() => send()}
        >
          <Upload size={15} />
          Validar y previsualizar
        </button>
      </div>
      {result && (
        <>
          <div className="admin-notice">
            {result.valid} filas válidas · {result.errors} errores ·{" "}
            {result.imported} empresas importadas
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Fila</th>
                  <th>Empresa</th>
                  <th>RUT</th>
                  <th>Resultado</th>
                </tr>
              </thead>
              <tbody>
                {(result.rows || []).map((r: RecordData) => (
                  <tr key={r.row}>
                    <td>{r.row}</td>
                    <td>{r.name || "—"}</td>
                    <td>{r.rut || "—"}</td>
                    <td>{r.valid ? "Correcta" : r.error}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!result.errors && !result.imported && (
            <div className="modal-actions">
              <button
                className="primary"
                disabled={busy}
                onClick={() => send(true)}
              >
                Importar {result.valid} empresas
              </button>
            </div>
          )}
        </>
      )}
    </Card>
  );
}
