"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Field } from "./ui";

export default function InitialSetup({ onComplete }: { onComplete: () => void }) {
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.slice(1));
    const value = params.get("setup");
    if (value) {
      setToken(value);
      // The key never travels in URLs to the server or stays in history.
      window.history.replaceState(null, "", window.location.pathname);
    }
  }, []);
  return (
    <>
      <h2>Creá tu administrador</h2>
      <p>Elegí tus credenciales para comenzar. No se crean clientes ni expedientes de ejemplo.</p>
      {!token && <div role="alert" className="alert">Abrí el enlace privado de inicio que se generó para tu entorno.</div>}
      <form method="post" onSubmit={async (event) => {
        event.preventDefault();
        setBusy(true);
        setError("");
        const form = event.currentTarget;
        const fields = new FormData(form);
        if (fields.get("password") !== fields.get("confirm")) {
          setError("Las contraseñas deben coincidir.");
          setBusy(false);
          return;
        }
        try {
          await api("/setup/admin", {
            method: "POST",
            headers: { "X-Setup-Token": token },
            body: JSON.stringify({ name: fields.get("name"), email: fields.get("email"), password: fields.get("password") }),
          });
          form.reset();
          setToken("");
          onComplete();
        } catch (exception) {
          setError((exception as Error).message);
        } finally {
          setBusy(false);
        }
      }}>
        <Field label="Tu nombre" name="name" required />
        <Field label="Correo electrónico" name="email" type="email" required />
        <Field label="Contraseña" name="password" type="password" required />
        <Field label="Repetir contraseña" name="confirm" type="password" required />
        <p>Usá entre 12 y 128 caracteres, con mayúsculas, minúsculas y números.</p>
        {error && <div role="alert" className="alert error">{error}</div>}
        <button className="primary full" disabled={busy || !token}>{busy ? "Creando…" : "Crear administrador"}</button>
      </form>
    </>
  );
}
