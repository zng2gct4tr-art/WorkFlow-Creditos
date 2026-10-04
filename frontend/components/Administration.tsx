"use client";
import { useEffect, useState } from "react";
import { Plus, ShieldCheck } from "lucide-react";
import { api, rows, RecordData } from "@/lib/api";
import { Card, Empty, Field } from "./ui";
const allowed: Record<string, string[]> = {
  users: ["name", "role_ids", "client_id", "active", "branch", "supervisor_id"],
  roles: ["name", "permissions"],
  products: ["name", "active"],
  profiles: ["name", "active", "rules"],
  requirements: [
    "profile_id",
    "name",
    "category",
    "mandatory",
    "validity_days",
    "rules",
    "conditions",
    "active",
  ],
  holidays: ["date", "name"],
  settings: ["key", "value"],
};
const sections = [
  ["users", "Usuarios"],
  ["roles", "Roles y permisos"],
  ["products", "Productos"],
  ["profiles", "Perfiles documentales"],
  ["requirements", "Requisitos"],
  ["holidays", "Feriados"],
  ["settings", "Parámetros"],
];
export default function Administration({
  onError,
}: {
  onError: (s: string) => void;
}) {
  const [section, setSection] = useState("users"),
    [data, setData] = useState<RecordData[]>([]),
    [modal, setModal] = useState(false),
    [busy, setBusy] = useState(false),
    [editing, setEditing] = useState<RecordData | null>(null),
    [editText, setEditText] = useState(""),
    [deleting, setDeleting] = useState<RecordData | null>(null);
  async function load() {
    try {
      setData(rows(await api(`/admin/${section}`)));
    } catch (e) {
      onError((e as Error).message);
    }
  }
  useEffect(() => {
    load();
  }, [section]);
  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    try {
      const f: any = Object.fromEntries(new FormData(e.currentTarget));
      if (section === "users" && !f.client_id) f.client_id = null;
      if (section === "roles")
        f.permissions = String(f.permissions || "")
          .split(",")
          .map((x: string) => x.trim())
          .filter(Boolean);
      if (section === "users")
        f.role_ids = String(f.role_ids || "")
          .split(",")
          .map((x: string) => x.trim())
          .filter(Boolean);
      if (section === "requirements") {
        f.mandatory = f.mandatory === "true";
        f.validity_days = Number(f.validity_days) || null;
      }
      if (section === "settings")
        try {
          f.value = JSON.parse(f.value);
        } catch {}
      await api(`/admin/${section}`, {
        method: "POST",
        body: JSON.stringify(f),
      });
      setModal(false);
      await load();
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="tabs">
        {sections.map(([id, name]) => (
          <button
            key={id}
            className={section === id ? "active" : ""}
            onClick={() => setSection(id)}
          >
            {name}
          </button>
        ))}
      </div>
      <Card
        title={sections.find((x) => x[0] === section)?.[1] || ""}
        action={
          <button className="primary" onClick={() => setModal(true)}>
            <Plus size={16} />
            Añadir
          </button>
        }
      >
        <div className="admin-notice">
          <ShieldCheck size={18} />
          Los cambios de configuración y permisos quedan registrados en
          auditoría.
        </div>
        {data.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Nombre / clave</th>
                  <th>Detalle</th>
                  <th>Identificador</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {data.map((r, i) => (
                  <tr key={r.id || i}>
                    <td>
                      <strong>{r.name || r.key || r.date}</strong>
                      <small>{r.email || r.code}</small>
                    </td>
                    <td>
                      {r.description ||
                        r.permissions?.join(", ") ||
                        JSON.stringify(r.value) ||
                        "—"}
                    </td>
                    <td className="mono">{r.id || "—"}</td>
                    <td>
                      <button
                        className="text-button"
                        onClick={() => {
                          setEditing(r);
                          const values = Object.fromEntries(
                            Object.entries(r).filter(([key]) =>
                              (allowed[section] || []).includes(key),
                            ),
                          );
                          setEditText(JSON.stringify(values, null, 2));
                        }}
                      >
                        Editar
                      </button>
                      {[
                        "users",
                        "products",
                        "profiles",
                        "requirements",
                        "holidays",
                      ].includes(section) && (
                        <button
                          className="text-button reject-text"
                          onClick={() => setDeleting(r)}
                        >
                          {section === "holidays" ? "Eliminar" : "Desactivar"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty />
        )}
      </Card>
      {editing && (
        <div className="modal-backdrop">
          <section
            className="modal small-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Editar configuración"
          >
            <h2>Editar {editing.name || editing.key}</h2>
            <p className="card-description">
              Modifica la configuración del registro. Conserva las claves
              necesarias.
            </p>
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                setBusy(true);
                try {
                  await api(
                    `/admin/${section}/${editing.id || editing.key || editing.date}`,
                    {
                      method: section === "users" ? "PATCH" : "PUT",
                      body: editText,
                    },
                  );
                  setEditing(null);
                  await load();
                } catch (e) {
                  onError((e as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              <label className="field">
                <span>Configuración</span>
                <textarea
                  rows={14}
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  required
                />
              </label>
              <div className="modal-actions">
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setEditing(null)}
                >
                  Cancelar
                </button>
                <button className="primary" disabled={busy}>
                  Guardar cambios
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
      {deleting && (
        <div className="modal-backdrop">
          <section
            className="modal small-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Desactivar registro"
          >
            <h2>Desactivar registro</h2>
            <p>
              Confirma la desactivación de {deleting.name || deleting.key}. La
              acción quedará registrada en auditoría.
            </p>
            <div className="modal-actions">
              <button className="secondary" onClick={() => setDeleting(null)}>
                Cancelar
              </button>
              <button
                className="danger"
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  try {
                    await api(
                      `/admin/${section}/${deleting.id || deleting.key || deleting.date}`,
                      { method: "DELETE" },
                    );
                    setDeleting(null);
                    await load();
                  } catch (e) {
                    onError((e as Error).message);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Desactivar
              </button>
            </div>
          </section>
        </div>
      )}
      {modal && (
        <div className="modal-backdrop">
          <section
            className="modal small-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="admin-modal-title"
          >
            <h2 id="admin-modal-title">
              Añadir {sections.find((x) => x[0] === section)?.[1].toLowerCase()}
            </h2>
            <form onSubmit={save}>
              <div className="form-grid">
                {section === "users" ? (
                  <>
                    <Field label="Nombre" name="name" required />
                    <Field label="Email" name="email" type="email" required />
                    <Field
                      label="Contraseña inicial"
                      name="password"
                      type="password"
                      required
                    />
                    <Field
                      label="IDs de roles (separados por coma)"
                      name="role_ids"
                      required
                    />
                    <Field
                      label="Empresa asociada (ID, solo clientes)"
                      name="client_id"
                    />
                  </>
                ) : section === "roles" ? (
                  <>
                    <Field label="Nombre del rol" name="name" required />
                    <Field
                      label="Permisos separados por coma"
                      name="permissions"
                      type="textarea"
                      required
                    />
                  </>
                ) : section === "holidays" ? (
                  <>
                    <Field label="Fecha" name="date" type="date" required />
                    <Field label="Descripción" name="name" required />
                  </>
                ) : section === "settings" ? (
                  <>
                    <Field label="Clave" name="key" required />
                    <Field
                      label="Valor"
                      name="value"
                      type="textarea"
                      required
                    />
                  </>
                ) : (
                  <>
                    <Field label="Nombre" name="name" required />
                    {section === "requirements" && (
                      <>
                        <Field
                          label="Perfil documental (ID)"
                          name="profile_id"
                          required
                        />
                        <Field label="Categoría" name="category" required />
                        <Field
                          label="Obligatorio"
                          name="mandatory"
                          options={[
                            { value: "true", label: "Sí" },
                            { value: "false", label: "No" },
                          ]}
                          required
                        />
                        <Field
                          label="Vigencia en días"
                          name="validity_days"
                          type="number"
                        />
                      </>
                    )}
                  </>
                )}
              </div>
              <div className="modal-actions">
                <button
                  className="secondary"
                  type="button"
                  onClick={() => setModal(false)}
                >
                  Cancelar
                </button>
                <button className="primary" disabled={busy}>
                  {busy ? "Guardando…" : "Guardar"}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </>
  );
}
