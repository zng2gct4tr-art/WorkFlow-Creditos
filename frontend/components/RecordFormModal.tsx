"use client";
import { RecordData } from "@/lib/api";
import { Field } from "./ui";
export default function RecordFormModal({
  modal,
  setModal,
  create,
  profiles,
  directory,
  user,
  selected,
  clients,
  catalog,
  error,
  busy,
}: {
  modal: string;
  setModal: (value: string) => void;
  create: (e: React.FormEvent<HTMLFormElement>) => Promise<void>;
  profiles: RecordData[];
  directory: RecordData[];
  user: RecordData;
  selected: RecordData | null;
  clients: RecordData[];
  catalog: RecordData[];
  error: string;
  busy: boolean;
}) {
  if (!modal) return null;
  return (
    <div className="modal-backdrop">
      <section
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
      >
        <div className="card-heading">
          <h2 id="modal-title">
            {modal === "client"
              ? "Registrar empresa"
              : "Crear propuesta de crédito"}
          </h2>
          <button
            className="icon-button"
            onClick={() => setModal("")}
            aria-label="Cerrar"
          >
            ×
          </button>
        </div>
        <form onSubmit={create}>
          <div className="form-grid">
            {modal === "client" ? (
              <>
                <Field label="Razón social" name="name" required />
                <Field label="RUT" name="rut" required />
                <Field
                  label="Número de cuenta"
                  name="account_number"
                  required
                />
                <Field label="Contacto principal" name="contact" />
                <Field label="Email" name="email" type="email" />
                <Field label="Teléfono" name="phone" />
                <Field label="Dirección" name="address" />
                <Field label="Actividad económica" name="activity" />
                <Field
                  label="Perfil documental"
                  name="profile_id"
                  required
                  options={profiles.map((x) => ({
                    value: x.id,
                    label: x.name,
                  }))}
                />
                <Field
                  label="Gestor comercial"
                  name="manager_id"
                  required
                  value={user.id}
                  options={directory.map((x) => ({
                    value: x.id,
                    label: x.name,
                  }))}
                />
                <Field label="Ingresos" name="income" type="number" />
                <Field label="Facturación" name="revenue" type="number" />
                <Field label="EBITDA" name="ebitda" type="number" />
                <Field label="Deuda total" name="total_debt" type="number" />
              </>
            ) : (
              <>
                <Field
                  label="Empresa"
                  name="client_id"
                  required
                  value={selected?._kind === "client" ? selected.id : ""}
                  options={clients.map((x) => ({
                    value: x.id,
                    label: x.name,
                  }))}
                />
                <Field
                  label="Producto"
                  name="product_id"
                  required
                  options={catalog.map((x) => ({
                    value: x.id,
                    label: x.name,
                  }))}
                />
                <Field
                  label="Importe solicitado"
                  name="amount"
                  type="number"
                  required
                />
                <Field
                  label="Moneda"
                  name="currency"
                  required
                  options={["USD", "UYU", "EUR"].map((x) => ({
                    value: x,
                    label: x,
                  }))}
                />
                <Field
                  label="Plazo (meses)"
                  name="term_months"
                  type="number"
                  required
                />
                <Field label="Tasa anual (%)" name="rate" type="number" />
                <Field
                  label="Finalidad"
                  name="purpose"
                  type="textarea"
                  required
                />
                <Field label="Garantías" name="guarantees" type="textarea" />
                <Field label="Forma de pago" name="payment_method" />
                <Field
                  label="Observaciones"
                  name="observations"
                  type="textarea"
                />
              </>
            )}
          </div>
          {error && (
            <div className="alert error" role="alert">
              {error}
            </div>
          )}
          <div className="modal-actions">
            <button
              type="button"
              className="secondary"
              onClick={() => setModal("")}
            >
              Cancelar
            </button>
            <button className="primary" disabled={busy}>
              {busy ? "Guardando…" : "Guardar registro"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
