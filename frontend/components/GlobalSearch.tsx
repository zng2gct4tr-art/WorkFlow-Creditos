"use client";
import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import { api, rows, RecordData } from "@/lib/api";
export default function GlobalSearch({
  onSelect,
}: {
  onSelect: (item: RecordData, kind: string) => void;
}) {
  const [q, setQ] = useState(""),
    [result, setResult] = useState<RecordData | null>(null);
  useEffect(() => {
    if (q.length < 2) {
      setResult(null);
      return;
    }
    const timeout = setTimeout(
      () =>
        api("/search?q=" + encodeURIComponent(q))
          .then(setResult)
          .catch(() => setResult(null)),
      350,
    );
    return () => clearTimeout(timeout);
  }, [q]);
  return (
    <div className="global-search">
      <Search size={15} />
      <input
        aria-label="Búsqueda global"
        placeholder="Buscar expediente, RUT, empresa…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      {result && (
        <div className="search-results">
          {(["clients", "proposals", "documents"] as const).map((key) => (
            <section key={key}>
              <h3>
                {key === "clients"
                  ? "Empresas"
                  : key === "proposals"
                    ? "Propuestas"
                    : "Documentos"}
              </h3>
              {rows(result[key]).map((item) => (
                <button
                  key={item.id}
                  onClick={() => {
                    if (key === "documents")
                      onSelect({ id: item.proposal_id }, "proposal");
                    else
                      onSelect(item, key === "clients" ? "client" : "proposal");
                    setQ("");
                    setResult(null);
                  }}
                >
                  <strong>{item.name || item.code || item.filename}</strong>
                  <small>{item.rut || item.client_name || item.state}</small>
                </button>
              ))}
              {!rows(result[key]).length && <p>Sin resultados</p>}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
