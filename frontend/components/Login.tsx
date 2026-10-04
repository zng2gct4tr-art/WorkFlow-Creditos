"use client";
import { ArrowUpRight, LockKeyhole, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import { Field } from "./ui";
import { useEffect, useState } from "react";
import InitialSetup from "./InitialSetup";
export default function Login({
  busy,
  error,
  notice,
  reset,
  resetToken,
  setBusy,
  setError,
  setNotice,
  setReset,
  setResetToken,
  login,
}: {
  busy: boolean;
  error: string;
  notice: string;
  reset: boolean;
  resetToken: string;
  setBusy: (value: boolean) => void;
  setError: (value: string) => void;
  setNotice: (value: string) => void;
  setReset: (value: boolean) => void;
  setResetToken: (value: string) => void;
  login: (e: React.FormEvent<HTMLFormElement>) => Promise<void>;
}) {
  const [initialSetup, setInitialSetup] = useState(false);
  useEffect(() => {
    let active = true;
    api("/setup/status").then((status) => {
      if (active) setInitialSetup(status.required === true);
    }).catch(() => {});
    return () => { active = false; };
  }, []);
  return (
    <main className="login">
      <div className="login-story">
        <div className="brand">
          <span className="brand-symbol">W</span>WorkFlow
          <span className="brand-light">Créditos</span>
        </div>
        <span className="eyebrow">BANCA EMPRESAS</span>
        <h1>
          Un proceso claro.
          <br />
          Decisiones con
          <br />
          <em>confianza.</em>
        </h1>
        <p>
          Conecta a tu equipo, controla cada expediente y acompaña a tus
          clientes en cada etapa.
        </p>
        <div className="login-proof">
          <ShieldCheck />
          Seguridad, trazabilidad y control operativo
        </div>
      </div>
      <div className="login-panel">
        <div className="login-form">
          <span className="eyebrow">ACCESO SEGURO</span>
          {initialSetup ? <InitialSetup onComplete={() => {
            setInitialSetup(false);
            setNotice("Administrador creado. Ingresá con el correo y la contraseña que elegiste.");
          }} /> : <>
          <h2>Bienvenido a WorkFlow</h2>
          <p>Ingresa con tu cuenta para continuar.</p>
          <form
            method="post"
            onSubmit={
              reset
                ? async (e) => {
                    e.preventDefault();
                    setBusy(true);
                    setError("");
                    try {
                      await api(
                        resetToken
                          ? "/auth/password/reset-confirm"
                          : "/auth/password/reset-request",
                        {
                          method: "POST",
                          body: JSON.stringify(
                            resetToken
                              ? {
                                  token: resetToken,
                                  password: new FormData(e.currentTarget).get(
                                    "password",
                                  ),
                                }
                              : Object.fromEntries(
                                  new FormData(e.currentTarget),
                                ),
                          ),
                        },
                      );
                      setNotice(
                        resetToken
                          ? "Contraseña actualizada. Ya puedes iniciar sesión."
                          : "Si existe una cuenta, recibirás instrucciones seguras por email.",
                      );
                      setResetToken("");
                      setReset(false);
                    } catch (e) {
                      setError((e as Error).message);
                    } finally {
                      setBusy(false);
                    }
                  }
                : login
            }
          >
            {resetToken ? (
              <Field
                label="Nueva contraseña (mínimo 12 caracteres)"
                name="password"
                type="password"
                required
              />
            ) : (
              <Field
                label="Correo electrónico"
                name="email"
                type="email"
                required
              />
            )}
            {!reset && (
              <Field
                label="Contraseña"
                name="password"
                type="password"
                required
              />
            )}
            {error && (
              <div role="alert" className="alert error">
                {error}
              </div>
            )}
            <button className="primary full" disabled={busy}>
              {busy
                ? "Procesando…"
                : reset
                  ? resetToken
                    ? "Guardar nueva contraseña"
                    : "Enviar instrucciones"
                  : "Iniciar sesión"}
              <ArrowUpRight size={18} />
            </button>
          </form>
          <button
            className="text-button reset-button"
            onClick={() => setReset(!reset)}
          >
            {reset ? "Volver al inicio de sesión" : "¿Olvidaste tu contraseña?"}
          </button>
          {notice && (
            <div className="alert success" role="status">
              {notice}
            </div>
          )}
          <p className="login-note">
            <LockKeyhole size={14} /> Tu sesión está protegida y se cierra por
            inactividad.
          </p>
          </>}
        </div>
        <span className="copyright">
          WorkFlow Créditos · Plataforma de banca corporativa
        </span>
      </div>
    </main>
  );
}
