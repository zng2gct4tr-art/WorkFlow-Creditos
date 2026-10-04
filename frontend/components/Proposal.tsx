"use client";
import { useEffect, useState, useRef } from "react";
import {
  ArrowLeft,
  Upload,
  Download,
  Check,
  FileText,
  MessageSquare,
  Clock,
  ShieldCheck,
  Sparkles,
  Send,
  Plus,
} from "lucide-react";
import { api, date, money, rows, RecordData } from "@/lib/api";
import { Badge, Card, Empty, Field } from "./ui";
import ReportAssessment from "./ReportAssessment";
export default function Proposal({
  proposal: p,
  user,
  onBack,
  onUpdate,
  onError,
}: {
  proposal: RecordData;
  user: RecordData;
  onBack: () => void;
  onUpdate: (p: RecordData) => void;
  onError: (s: string) => void;
}) {
  const [tab, setTab] = useState("summary"),
    [busy, setBusy] = useState(false),
    [comments, setComments] = useState<RecordData[]>([]),
    [content, setContent] = useState(p.report?.content || ""),
    [reason, setReason] = useState(""),
    [action, setAction] = useState(""),
    [analysts, setAnalysts] = useState<RecordData[]>([]);
  const [editing, setEditing] = useState(false),
    [saved, setSaved] = useState("");
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    },
    [],
  );
  const portal = Boolean(user.client_id);
  const can = (permission: string) =>
    (!portal && (user.permissions || []).includes(permission)) ||
    (!portal && (user.permissions || []).includes("*"));
  async function refresh() {
    onUpdate(await api(`/proposals/${p.id}`));
  }
  async function run(fn: () => Promise<any>) {
    setBusy(true);
    onError("");
    try {
      await fn();
      await refresh();
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    if (tab === "conversation" && !portal)
      api(`/proposals/${p.id}/comments`)
        .then((x) => setComments(rows(x)))
        .catch((e) => onError(e.message));
    if (tab === "assignment" && !portal)
      api("/catalog")
        .then((x) => setAnalysts(rows(x.users).filter((u) => u.can_analyze)))
        .catch((e) => onError(e.message));
  }, [tab, p.id]);
  const allActions = portal
    ? []
    : p.state === "draft" || p.state === "documentation_pending"
      ? [
          ["prepare", "Revisar documentación"],
          ["cancel", "Cancelar propuesta"],
        ]
      : p.state === "ready"
        ? [
            ["submit", "Enviar a Riesgos"],
            ["cancel", "Cancelar propuesta"],
          ]
        : ["in_analysis", "reanalysis"].includes(p.state)
          ? [
              ["request_information", "Solicitar ampliación"],
              ["approve", "Aprobar crédito"],
              ["reject", "Rechazar crédito"],
            ]
          : p.state === "additional_requested"
            ? [["resubmit", "Reenviar a Riesgos"]]
            : p.state === "rejected"
              ? [["reopen", "Reabrir propuesta"]]
              : [];
  const actionPermissions: Record<string, string> = {
    prepare: "proposal.edit",
    submit: "proposal.submit",
    request_information: "risk.request",
    resubmit: "proposal.submit",
    approve: "risk.approve",
    reject: "risk.reject",
    cancel: "proposal.cancel",
    reopen: "proposal.reopen",
  };
  const actions = allActions.filter(([id]) => can(actionPermissions[id]));
  return (
    <>
      <button className="back" onClick={onBack}>
        <ArrowLeft size={16} />
        Volver a propuestas
      </button>
      <div className="page-heading">
        <div>
          <span className="eyebrow">EXPEDIENTE DE CRÉDITO</span>
          <h1>
            {p.code}
            <Badge value={p.state} />
          </h1>
          <p>
            {p.client_name} · {p.product_name}
            {!portal && <> · Versión {p.version}</>}
          </p>
        </div>
        <strong className="proposal-amount">
          {money(p.amount, p.currency)}
          <small>Importe solicitado</small>
        </strong>
      </div>
      <div className="proposal-strip">
        <div>
          <span>Responsable actual</span>
          <strong>
            {["approved", "rejected", "cancelled"].includes(p.state)
              ? "Proceso finalizado"
              : ["in_analysis", "reanalysis"].includes(p.state)
                ? "Equipo de Riesgos"
                : "Gestión comercial"}
          </strong>
        </div>
        <div>
          <span>Completitud documental</span>
          <strong>{p.completeness ?? 0}%</strong>
        </div>
        <div>
          <span>Validez documental</span>
          <strong>
            {p.validity === true || p.validity === "approved"
              ? "Aprobada"
              : "Pendiente de validación"}
          </strong>
        </div>
        <div>
          <span>Siguiente paso</span>
          <strong>
            {actions[0]?.[1] || "Consulta el estado de tu solicitud"}
          </strong>
        </div>
      </div>
      <div className="tabs" role="tablist">
        {[
          ["summary", "Resumen"],
          ["documents", "Documentación"],
          ...(!portal
            ? [
                ["report", "Informe comercial"],
                ["conversation", "Conversación interna"],
                ...(can("assignment.manage")
                  ? [["assignment", "Asignación"]]
                  : []),
              ]
            : []),
        ].map(([id, label]) => (
          <button
            key={id}
            role="tab"
            aria-selected={tab === id}
            className={tab === id ? "active" : ""}
            onClick={() => setTab(id)}
          >
            {label}
            {id === "documents" && <span>{rows(p.requirements).length}</span>}
          </button>
        ))}
      </div>
      {tab === "summary" ? (
        <>
          <div className="two-columns">
            <Card
              title="Condiciones de la operación"
              action={
                !portal &&
                can("proposal.edit") &&
                [
                  "draft",
                  "documentation_pending",
                  "ready",
                  "additional_requested",
                ].includes(p.state) ? (
                  <button
                    className="text-button"
                    onClick={() => setEditing(!editing)}
                  >
                    {editing ? "Ver resumen" : "Editar borrador"}
                  </button>
                ) : undefined
              }
            >
              {editing ? (
                <form
                  onSubmit={(e) => e.preventDefault()}
                  onChange={(e) => {
                    const form = e.currentTarget;
                    if (saveTimer.current) clearTimeout(saveTimer.current);
                    setSaved("Cambios pendientes…");
                    saveTimer.current = setTimeout(() => {
                      const values: any = Object.fromEntries(
                        new FormData(form),
                      );
                      values.term_months = Number(values.term_months);
                      run(async () => {
                        await api(`/proposals/${p.id}`, {
                          method: "PATCH",
                          body: JSON.stringify({
                            ...values,
                            version: p.version,
                          }),
                        });
                        setSaved("Borrador guardado");
                      });
                    }, 1200);
                  }}
                >
                  <div className="form-grid">
                    <Field
                      label="Importe"
                      name="amount"
                      type="number"
                      required
                      value={p.amount}
                    />
                    <Field
                      label="Moneda"
                      name="currency"
                      required
                      value={p.currency}
                      options={["USD", "UYU", "EUR"].map((x) => ({
                        value: x,
                        label: x,
                      }))}
                    />
                    <Field
                      label="Plazo en meses"
                      name="term_months"
                      type="number"
                      required
                      value={p.term_months}
                    />
                    <Field
                      label="Tasa anual"
                      name="rate"
                      type="number"
                      value={p.rate}
                    />
                    <Field
                      label="Finalidad"
                      name="purpose"
                      type="textarea"
                      required
                      value={p.purpose}
                    />
                    <Field
                      label="Garantías"
                      name="guarantees"
                      type="textarea"
                      value={p.guarantees}
                    />
                    <Field
                      label="Forma de pago"
                      name="payment_method"
                      value={p.payment_method}
                    />
                    <Field
                      label="Observaciones"
                      name="observations"
                      type="textarea"
                      value={p.observations}
                    />
                  </div>
                  <p className="autosave" role="status">
                    {saved || "Los cambios se guardan automáticamente."}
                  </p>
                </form>
              ) : (
                <dl className="details">
                  {[
                    ["Producto", p.product_name],
                    ["Plazo", `${p.term_months} meses`],
                    ["Tasa", p.rate != null ? `${p.rate}%` : "—"],
                    ["Finalidad", p.purpose],
                    ["Garantías", p.guarantees],
                    ["Forma de pago", p.payment_method],
                    ["Observaciones", p.observations],
                  ].map(([k, v]) => (
                    <div key={k}>
                      <dt>{k}</dt>
                      <dd>{v || "—"}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </Card>
            <Card title="Seguimiento de plazos">
              <div className="sla-list">
                {Object.entries(p.sla || {}).map(([k, v]: [string, any]) => (
                  <div className="sla-item" key={k}>
                    <div>
                      <Clock size={20} />
                      <strong>
                        {k === "commercial"
                          ? "Gestión comercial"
                          : "Análisis de Riesgos"}
                      </strong>
                      <Badge
                        value={v.paused ? "paused" : v.color || "pending"}
                      />
                    </div>
                    <p>
                      {v.started_at
                        ? `Inicio: ${date(v.started_at)}`
                        : "El contador se iniciará cuando corresponda."}
                    </p>
                    <div className="progress">
                      <i
                        style={{ width: `${Math.min(100, v.percent || 0)}%` }}
                      />
                    </div>
                    <small>
                      {v.consumed ?? 0} /{" "}
                      {v.allowance || (k === "commercial" ? 7 : 15)} días
                      hábiles · {v.remaining ?? 0} restantes
                    </small>
                  </div>
                ))}
              </div>
            </Card>
          </div>
          {actions.length > 0 && (
            <Card title="Acciones del expediente">
              <p className="card-description">
                Las decisiones y sus motivos quedan registrados en el historial
                del expediente.
              </p>
              <div className="action-buttons">
                {actions.map(([id, label]) => (
                  <button
                    className={
                      id === "approve" || id === "submit"
                        ? "primary"
                        : id === "reject" || id === "cancel"
                          ? "danger"
                          : "secondary"
                    }
                    key={id}
                    onClick={() => {
                      setAction(id);
                      setReason("");
                    }}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </Card>
          )}
        </>
      ) : tab === "documents" ? (
        <Card
          title="Checklist documental"
          action={
            <span className="count">{p.completeness ?? 0}% recibido</span>
          }
        >
          <p className="card-description">
            Carga los archivos correspondientes a cada requisito. Recibir un
            documento y validar su contenido son pasos independientes.
          </p>
          {rows(p.requirements).length ? (
            rows(p.requirements).map((r) => (
              <div className="requirement" key={r.id}>
                <div className="requirement-header">
                  <span className="document-icon">
                    <FileText size={21} />
                  </span>
                  <div>
                    <h3>{r.name}</h3>
                    <small>
                      {r.category} · {r.mandatory ? "Obligatorio" : "Opcional"}
                    </small>
                  </div>
                  <Badge value={r.status} />
                  <label className="secondary upload-button">
                    <Upload size={15} />
                    Cargar archivo
                    <input
                      aria-label={`Cargar ${r.name}`}
                      type="file"
                      disabled={busy}
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file)
                          run(async () => {
                            const form = new FormData();
                            form.append("file", file);
                            await api(`/requirements/${r.id}/documents`, {
                              method: "POST",
                              body: form,
                            });
                          });
                      }}
                    />
                  </label>
                </div>
                {rows(r.documents).map((d) => (
                  <div className="document-file" key={d.id}>
                    <FileText size={16} />
                    <div>
                      <strong>{d.name || d.filename}</strong>
                      <small>
                        {date(d.created_at)}
                        {d.observations ? ` · ${d.observations}` : ""}
                      </small>
                      {d.extraction?.warnings?.length > 0 && (
                        <p className="document-warning">
                          {d.extraction.warnings.join(" · ")}
                        </p>
                      )}
                    </div>
                    <Badge value={d.status} />
                    {["incorrect", "expired"].includes(d.status) && (
                      <label className="secondary upload-button">
                        <Upload size={15} />
                        Sustituir
                        <input
                          type="file"
                          aria-label={`Sustituir ${d.name}`}
                          disabled={busy}
                          onChange={(e) => {
                            const file = e.target.files?.[0];
                            if (file)
                              run(async () => {
                                const form = new FormData();
                                form.append("file", file);
                                form.append("replace_id", d.id);
                                await api(`/requirements/${r.id}/documents`, {
                                  method: "POST",
                                  body: form,
                                });
                              });
                          }}
                        />
                      </label>
                    )}
                    <button
                      className="icon-button"
                      aria-label="Descargar documento"
                      onClick={() =>
                        run(async () => {
                          const result = await api(
                            `/documents/${d.id}/download-url`,
                          );
                          const url = new URL(
                            result.url,
                            window.location.origin,
                          );
                          if (
                            url.origin !== window.location.origin &&
                            !url.href.startsWith("https://")
                          )
                            throw new Error(
                              "El enlace de descarga no es seguro.",
                            );
                          window.open(
                            url.href,
                            "_blank",
                            "noopener,noreferrer",
                          );
                        })
                      }
                    >
                      <Download size={17} />
                    </button>
                    {can("document.validate") && (
                      <>
                        <button
                          className="text-button"
                          onClick={() => {
                            setAction(`validate:${d.id}:correct`);
                            setReason("");
                          }}
                        >
                          Validar
                        </button>
                        <button
                          className="text-button reject-text"
                          onClick={() => {
                            setAction(`validate:${d.id}:incorrect`);
                            setReason("");
                          }}
                        >
                          Rechazar
                        </button>
                      </>
                    )}
                  </div>
                ))}
                {!rows(r.documents).length && (
                  <p className="requirement-empty">
                    Aún no se recibieron archivos para este requisito.
                  </p>
                )}
              </div>
            ))
          ) : (
            <Empty title="Sin requisitos" />
          )}
        </Card>
      ) : tab === "report" ? (
        <Card
          title="Informe comercial"
          action={
            <button
              className="secondary"
              disabled={busy || !can("proposal.edit")}
              onClick={() =>
                run(async () => {
                  const result = await api(`/proposals/${p.id}/report/assist`, {
                    method: "POST",
                  });
                  setContent(result.ai_content || result.content || "");
                })
              }
            >
              <Sparkles size={16} />
              Asistir con IA
            </button>
          }
        >
          <p className="card-description">
            Revisa y edita las sugerencias antes de guardar la versión
            definitiva. La evaluación automática se distingue de la revisión
            humana.
          </p>
          <label className="field">
            <span>Análisis comercial</span>
            <textarea
              rows={14}
              value={content}
              onChange={(e) => setContent(e.target.value)}
              readOnly={
                !can("proposal.edit") ||
                ![
                  "draft",
                  "documentation_pending",
                  "ready",
                  "additional_requested",
                ].includes(p.state)
              }
            />
          </label>
          <div className="modal-actions">
            <button
              className="secondary"
              disabled={busy || !can("proposal.edit")}
              onClick={() =>
                run(() =>
                  api(`/proposals/${p.id}/report`, {
                    method: "POST",
                    body: JSON.stringify({ content, final: false }),
                  }),
                )
              }
            >
              Guardar borrador
            </button>
            <button
              className="primary"
              disabled={busy || !content.trim() || !can("proposal.edit")}
              onClick={() =>
                run(() =>
                  api(`/proposals/${p.id}/report`, {
                    method: "POST",
                    body: JSON.stringify({ content, final: true }),
                  }),
                )
              }
            >
              <Check size={16} />
              Guardar versión final
            </button>
          </div>
          <ReportAssessment
            proposal={p}
            onSave={refresh}
            onError={onError}
            allowed={can("report.assess")}
          />
          {p.report?.quality_score != null && (
            <p className="quality-score">
              Evaluación automática del informe: {p.report.quality_score}/100
            </p>
          )}
        </Card>
      ) : tab === "conversation" ? (
        <Card
          title="Conversación interna"
          action={
            <span className="private-label">
              <ShieldCheck size={14} />
              Solo equipo autorizado
            </span>
          }
        >
          <div className="conversation">
            {comments.length ? (
              comments.map((c) => (
                <div className="message" key={c.id}>
                  <span className="avatar">
                    {(c.user_name || c.author_name || "US").slice(0, 2)}
                  </span>
                  <div>
                    <strong>
                      {c.user_name || c.author_name || "Usuario interno"}
                    </strong>
                    <small>{date(c.created_at)}</small>
                    <p>{c.content}</p>
                    {rows(c.attachments).map((a) => (
                      <button
                        className="text-button"
                        key={a.id}
                        onClick={() =>
                          run(async () => {
                            const result = await api(
                              `/documents/${a.document_id}/download-url`,
                            );
                            window.open(
                              result.url,
                              "_blank",
                              "noopener,noreferrer",
                            );
                          })
                        }
                      >
                        <Download size={13} />
                        Documento adjunto
                      </button>
                    ))}
                  </div>
                </div>
              ))
            ) : (
              <Empty
                title="Inicia la conversación"
                description="Comparte información relevante para el análisis. Este canal no es visible para el cliente."
              />
            )}
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const form = e.currentTarget;
              const formData = new FormData(form);
              const text = formData.get("content");
              const attachment_ids = formData.getAll("attachment_ids");
              run(async () => {
                await api(`/proposals/${p.id}/comments`, {
                  method: "POST",
                  body: JSON.stringify({ content: text, attachment_ids }),
                });
                setComments(rows(await api(`/proposals/${p.id}/comments`)));
                form.reset();
              });
            }}
            className="message-form"
          >
            <label className="sr-only" htmlFor="message-content">
              Mensaje interno
            </label>
            <textarea
              id="message-content"
              name="content"
              placeholder="Escribe un mensaje para el equipo…"
              required
              rows={3}
            />
            <label className="field attachment-select">
              <span>Adjuntar documentos del expediente (opcional)</span>
              <select
                multiple
                name="attachment_ids"
                aria-label="Documentos adjuntos"
              >
                {rows(p.requirements)
                  .flatMap((r) => rows(r.documents))
                  .map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
              </select>
            </label>
            <button className="primary" disabled={busy}>
              <Send size={16} />
              Enviar mensaje
            </button>
          </form>
        </Card>
      ) : (
        <Card title="Asignación de analistas">
          <p className="card-description">
            Asigna responsables de Riesgos y documenta el motivo de la
            asignación o reasignación.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              run(() =>
                api(`/proposals/${p.id}/assign`, {
                  method: "POST",
                  body: JSON.stringify({
                    analyst_ids: f.getAll("analyst_ids"),
                    reason: f.get("reason"),
                  }),
                }),
              );
            }}
          >
            <div className="analyst-options">
              {analysts.map((a) => (
                <label key={a.id}>
                  <input
                    type="checkbox"
                    name="analyst_ids"
                    value={a.id}
                    defaultChecked={rows(p.assignments).some(
                      (x) => x.user_id === a.id,
                    )}
                  />
                  <span>
                    {a.name}
                    <small>{a.email}</small>
                  </span>
                </label>
              ))}
            </div>
            <Field
              label="Motivo de la asignación"
              name="reason"
              type="textarea"
              required
            />
            <button className="primary" disabled={busy}>
              Guardar asignación
            </button>
          </form>
        </Card>
      )}
      {action && (
        <div className="modal-backdrop">
          <section
            className="modal small-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="action-title"
          >
            <h2 id="action-title">
              {action.startsWith("validate")
                ? "Revisión humana del documento"
                : actions.find((x) => x[0] === action)?.[1]}
            </h2>
            <p>
              Describe el motivo. Esta acción quedará registrada con tu
              identidad y fecha.
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                run(async () => {
                  if (action.startsWith("validate")) {
                    const [, id, status] = action.split(":");
                    await api(`/documents/${id}/validate`, {
                      method: "POST",
                      body: JSON.stringify({ status, reason }),
                    });
                  } else
                    await api(`/proposals/${p.id}/transition`, {
                      method: "POST",
                      body: JSON.stringify({
                        action,
                        reason,
                        version: p.version,
                      }),
                    });
                  setAction("");
                });
              }}
            >
              <label className="field">
                <span>Justificación</span>
                <textarea
                  required
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  rows={4}
                />
              </label>
              <div className="modal-actions">
                <button
                  className="secondary"
                  type="button"
                  onClick={() => setAction("")}
                >
                  Volver
                </button>
                <button className="primary" disabled={busy || !reason.trim()}>
                  Confirmar acción
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </>
  );
}
