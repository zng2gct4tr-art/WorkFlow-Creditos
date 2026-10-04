"use client";
import { useState } from "react";
import { api, RecordData } from "@/lib/api";
import { Field } from "./ui";
const rubric = [
  ["completeness", "Completitud"],
  ["coherence", "Coherencia"],
  ["analysis", "Calidad del análisis"],
  ["financial_consistency", "Consistencia financiera"],
  ["risk_identification", "Identificación de riesgos"],
  ["clarity", "Claridad"],
];
export default function ReportAssessment({
  proposal,
  onSave,
  onError,
  allowed,
}: {
  proposal: RecordData;
  onSave: () => Promise<void>;
  onError: (s: string) => void;
  allowed: boolean;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <section className="assessment">
      <h3>Calidad del informe comercial</h3>
      <div className="assessment-scores">
        <div>
          <span>Evaluación automática</span>
          <strong>
            {proposal.report?.ai_assessment?.score ??
              proposal.report?.ai_assessment?.weighted_score ??
              "Sin evaluación"}
          </strong>
        </div>
        <div>
          <span>Evaluación humana</span>
          <strong>
            {proposal.report?.human_assessment?.weighted_score ??
              proposal.report?.human_assessment?.score ??
              "Pendiente de revisión"}
          </strong>
        </div>
      </div>
      {allowed && proposal.report && (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const f = Object.fromEntries(new FormData(e.currentTarget));
            const scores = Object.fromEntries(
              Object.entries(f).map(([k, v]) => [k, Number(v)]),
            );
            setBusy(true);
            try {
              await api(`/proposals/${proposal.id}/report/assessment`, {
                method: "POST",
                body: JSON.stringify(scores),
              });
              await onSave();
            } catch (e) {
              onError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <p>
            Califica cada criterio de 0 a 100. La revisión conservará tu
            identidad y fecha.
          </p>
          <div className="form-grid">
            {rubric.map(([key, label]) => (
              <Field
                key={key}
                label={label}
                name={key}
                type="number"
                required
                value={proposal.report?.human_assessment?.scores?.[key] ?? 0}
              />
            ))}
          </div>
          <button className="secondary" disabled={busy}>
            Guardar evaluación humana
          </button>
        </form>
      )}
    </section>
  );
}
