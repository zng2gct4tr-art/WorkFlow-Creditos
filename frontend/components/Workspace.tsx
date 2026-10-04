"use client";
import { useEffect, useState, useRef } from "react";
import {
  LayoutDashboard,
  Users,
  Files,
  ClipboardCheck,
  ChartNoAxesCombined,
  ShieldCheck,
  Settings,
  Bell,
  Search,
  ArrowUpRight,
  LogOut,
  ChevronDown,
  Plus,
  Menu,
  Sun,
  Moon,
  Building2,
  ArrowLeft,
  Download,
  Check,
  Clock,
  LockKeyhole,
  BriefcaseBusiness,
} from "lucide-react";
import { api, rows, money, date, labels, RecordData } from "@/lib/api";
import { Badge, Card, Empty, Field, RowAction } from "./ui";
import Proposal from "./Proposal";
import Administration from "./Administration";
import ClientImport from "./ClientImport";
import GlobalSearch from "./GlobalSearch";
import Login from "./Login";
import RecordFormModal from "./RecordFormModal";
import ClientDetail from "./ClientDetail";
import ReportsPanel from "./ReportsPanel";
import AuditTable from "./AuditTable";
import RecordsList from "./RecordsList";
import Dashboard from "./Dashboard";
import { useSessionTimeout } from "@/lib/useSessionTimeout";
import ReportFilters, {
  filterQuery,
  ReportFilterValues,
} from "./ReportFilters";
import OperationalMetrics from "./OperationalMetrics";
const navigation = [
  { id: "dashboard", title: "Resumen general", icon: LayoutDashboard },
  { id: "clients", title: "Mis clientes", icon: Users },
  { id: "proposals", title: "Propuestas de crédito", icon: Files },
  { id: "analysis", title: "Bandeja de análisis", icon: ClipboardCheck },
  { id: "reports", title: "Reportes", icon: ChartNoAxesCombined },
  { id: "audit", title: "Auditoría", icon: ShieldCheck },
  { id: "admin", title: "Administración", icon: Settings },
];
export default function Workspace() {
  const [user, setUser] = useState<RecordData | null>(null),
    [loading, setLoading] = useState(true),
    [view, setView] = useState("dashboard"),
    [data, setData] = useState<any>(null),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [selected, setSelected] = useState<RecordData | null>(null),
    [modal, setModal] = useState(""),
    [catalog, setCatalog] = useState<RecordData[]>([]),
    [clients, setClients] = useState<RecordData[]>([]),
    [profiles, setProfiles] = useState<RecordData[]>([]),
    [directory, setDirectory] = useState<RecordData[]>([]),
    [query, setQuery] = useState(""),
    [status, setStatus] = useState(""),
    [mobile, setMobile] = useState(false),
    [dark, setDark] = useState(false),
    [reset, setReset] = useState(false),
    [resetToken, setResetToken] = useState("");
  const [reportFilters, setReportFilters] = useState<ReportFilterValues>({});
  const sessionUser = useRef(user);
  sessionUser.current = user;
  function lockSession() {
    if (!sessionUser.current) return;
    sessionUser.current = null;
    setUser(null);
    setSelected(null);
    setData(null);
    setCatalog([]);
    setClients([]);
    setProfiles([]);
    setDirectory([]);
    setModal("");
    setQuery("");
    setStatus("");
    setNotice("");
    setError("Tu sesión finalizó por inactividad. Inicia sesión nuevamente.");
    setReportFilters({});
  }
  useSessionTimeout(Boolean(user), () => {
    lockSession();
    api("/auth/logout", { method: "POST" }).catch(() => {});
  });
  useEffect(() => {
    const expired = () => lockSession();
    window.addEventListener("wf-session-expired", expired);
    return () => window.removeEventListener("wf-session-expired", expired);
  }, []);
  const clientPortal = Boolean(user?.client_id);
  async function load(next = view) {
    setLoading(true);
    setError("");
    try {
      const path =
        next === "dashboard"
          ? "/reports/dashboard"
          : next === "clients"
            ? "/clients"
            : next === "reports"
              ? "/reports/dashboard"
              : next === "audit"
                ? "/audit"
                : next === "notifications"
                  ? "/notifications"
                  : next === "profile"
                    ? "/auth/me"
                    : next === "admin"
                      ? "/admin/users"
                      : "/proposals";
      const currentUserId = sessionUser.current?.id;
      const query =
        next === "dashboard" || next === "reports"
          ? filterQuery(reportFilters)
          : "";
      const result = await api(path + (query ? "?" + query : ""));
      if (sessionUser.current?.id === currentUserId) setData(result);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get("token");
    if (token) {
      setResetToken(token);
      setReset(true);
    }
    api("/auth/me")
      .then((u) => {
        setUser(u);
        setView(u.client_id ? "proposals" : "dashboard");
      })
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    if (user) load();
  }, [user, view, reportFilters]);
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
  }, [dark]);
  function go(next: string) {
    setView(next);
    setSelected(null);
    setQuery("");
    setStatus("");
    setMobile(false);
  }
  async function login(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const f = new FormData(e.currentTarget);
    try {
      await api("/auth/login", {
        method: "POST",
        body: JSON.stringify(Object.fromEntries(f)),
      });
      const u = await api("/auth/me");
      setUser(u);
      setView(u.client_id ? "proposals" : "dashboard");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function detail(item: RecordData, kind = "proposal") {
    setError("");
    try {
      const result = await api(
        `/${kind === "client" ? "clients" : "proposals"}/${item.id}`,
      );
      if (sessionUser.current) setSelected({ ...result, _kind: kind });
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function create(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const f = Object.fromEntries(new FormData(e.currentTarget));
    const payload: any = { ...f };
    if (modal === "client") {
      payload.financials = {};
      for (const key of [
        "income",
        "revenue",
        "ebitda",
        "total_debt",
        "bbva_debt",
      ]) {
        if (key in payload) {
          if (payload[key] !== "") payload.financials[key] = payload[key];
          delete payload[key];
        }
      }
    }
    if ("term_months" in payload)
      payload.term_months = Number(payload.term_months);
    try {
      await api(modal === "client" ? "/clients" : "/proposals", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setModal("");
      setNotice("Registro guardado correctamente.");
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function newProposal() {
    try {
      const cat = await api("/catalog");
      setCatalog(rows(cat.products));
      setClients(rows(await api("/clients")));
      setModal("proposal");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  if (!user)
    return (
      <Login
        busy={busy}
        error={error}
        notice={notice}
        reset={reset}
        resetToken={resetToken}
        setBusy={setBusy}
        setError={setError}
        setNotice={setNotice}
        setReset={setReset}
        setResetToken={setResetToken}
        login={login}
      />
    );
  const filtered = rows(data)
    .filter(
      (x) =>
        (!query ||
          JSON.stringify(x).toLowerCase().includes(query.toLowerCase())) &&
        (!status || x.state === status),
    )
    .filter(
      (x) =>
        view !== "analysis" ||
        ["in_analysis", "reanalysis", "additional_requested"].includes(x.state),
    );
  const stats = data || {};
  return (
    <div className="workspace">
      <aside className={`sidebar ${mobile ? "open" : ""}`}>
        <a
          href="#"
          className="brand"
          onClick={() => go(clientPortal ? "proposals" : "dashboard")}
        >
          <span className="brand-symbol">W</span>
          <span>
            WorkFlow<small>CRÉDITOS</small>
          </span>
        </a>
        <div className="workspace-label">
          {clientPortal ? "PORTAL EMPRESAS" : "ESPACIO DE TRABAJO"}
        </div>
        <nav>
          {(clientPortal
            ? navigation.filter((x) => ["clients", "proposals"].includes(x.id))
            : navigation.filter(
                (n) =>
                  n.id === "dashboard" ||
                  n.id === "clients" ||
                  n.id === "proposals" ||
                  (n.id === "analysis" &&
                    (user.permissions || []).includes("risk.view")) ||
                  (n.id === "reports" &&
                    (user.permissions || []).includes("report.view")) ||
                  (n.id === "audit" &&
                    (user.permissions || []).includes("audit.view")) ||
                  (n.id === "admin" &&
                    (user.permissions || []).some((p: string) =>
                      ["user.manage", "role.manage", "config.manage"].includes(
                        p,
                      ),
                    )),
              )
          ).map((n) => (
            <button
              key={n.id}
              className={view === n.id ? "nav active" : "nav"}
              onClick={() => go(n.id)}
            >
              <n.icon size={19} />
              {clientPortal && n.id === "clients" ? "Mi empresa" : n.title}
              {view === n.id && <span className="nav-dot" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="secure-note">
            <ShieldCheck size={20} />
            <div>
              Entorno protegido<small>Acceso según tus permisos</small>
            </div>
          </div>
          <button className="user-chip" onClick={() => go("profile")}>
            <span className="avatar">
              {user.name?.slice(0, 2).toUpperCase() || "US"}
            </span>
            <span>
              {user.name}
              <small>
                {clientPortal ? "Cliente empresa" : "Equipo de banca empresas"}
              </small>
            </span>
            <ChevronDown size={15} />
          </button>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <button
            className="icon-button mobile-toggle"
            onClick={() => setMobile(!mobile)}
            aria-label="Abrir menú"
          >
            <Menu />
          </button>
          <div className="breadcrumb">
            Banca empresas <span>/</span>{" "}
            {navigation.find((n) => n.id === view)?.title || "Mi cuenta"}
          </div>
          <div className="top-actions">
            <GlobalSearch onSelect={detail} />
            <button
              className="icon-button"
              aria-label="Cambiar tema"
              onClick={() => setDark(!dark)}
            >
              {dark ? <Sun size={19} /> : <Moon size={19} />}
            </button>
            <button
              className="icon-button notification-button"
              aria-label="Notificaciones"
              onClick={() => go("notifications")}
            >
              <Bell size={20} />
            </button>
            <span className="top-avatar">{user.name?.slice(0, 1)}</span>
          </div>
        </header>
        <main className="content">
          {error && (
            <div role="alert" className="alert error">
              {error}
              <button onClick={() => setError("")} aria-label="Cerrar">
                ×
              </button>
            </div>
          )}
          {notice && (
            <div role="status" className="alert success">
              {notice}
              <button onClick={() => setNotice("")} aria-label="Cerrar">
                ×
              </button>
            </div>
          )}
          {selected ? (
            selected._kind === "proposal" ? (
              <Proposal
                proposal={selected}
                user={user}
                onBack={() => setSelected(null)}
                onUpdate={(p) => setSelected({ ...p, _kind: "proposal" })}
                onError={setError}
              />
            ) : (
              <ClientDetail
                selected={selected}
                setSelected={setSelected}
                clientPortal={clientPortal}
                newProposal={newProposal}
                detail={detail}
              />
            )
          ) : (
            <>
              <div className="page-heading">
                <div>
                  <span className="eyebrow">
                    {clientPortal
                      ? "TU EMPRESA, CONECTADA"
                      : "CONTROL Y VISIBILIDAD"}
                  </span>
                  <h1>
                    {view === "dashboard"
                      ? "Tu operación, en perspectiva"
                      : view === "analysis"
                        ? "Bandeja de análisis"
                        : view === "profile"
                          ? "Mi perfil"
                          : view === "notifications"
                            ? "Notificaciones"
                            : clientPortal
                              ? "Tu solicitud de crédito"
                              : navigation.find((n) => n.id === view)?.title}
                  </h1>
                  <p>
                    {view === "dashboard"
                      ? "Cada expediente, cada etapa y cada decisión en un solo lugar."
                      : view === "clients"
                        ? "Gestiona tu cartera de empresas y sus operaciones."
                        : view === "proposals"
                          ? "Acompaña cada solicitud desde el inicio hasta la decisión."
                          : view === "analysis"
                            ? "Revisa expedientes y prioriza las próximas acciones."
                            : "Información confiable para actuar con claridad."}
                  </p>
                </div>
                {!clientPortal &&
                  ["clients", "proposals"].includes(view) &&
                  (user.permissions || []).includes(
                    view === "clients" ? "client.create" : "proposal.create",
                  ) && (
                    <button
                      className="primary"
                      onClick={() =>
                        view === "clients"
                          ? api("/catalog")
                              .then((cat) => {
                                setProfiles(rows(cat.profiles));
                                setDirectory(rows(cat.users));
                                setModal("client");
                              })
                              .catch((e) => setError(e.message))
                          : newProposal()
                      }
                    >
                      <Plus size={18} />
                      {view === "clients" ? "Nueva empresa" : "Nueva propuesta"}
                    </button>
                  )}
              </div>
              {["dashboard", "reports"].includes(view) && !clientPortal && (
                <ReportFilters
                  key={JSON.stringify(reportFilters)}
                  values={reportFilters}
                  onApply={setReportFilters}
                  onError={setError}
                />
              )}
              {view === "clients" &&
                !clientPortal &&
                (user.permissions || []).includes("client.import") && (
                  <details className="import-disclosure">
                    <summary>Importar empresas desde CSV o Excel</summary>
                    <ClientImport
                      onDone={() => {
                        load();
                        setNotice("Empresas importadas correctamente.");
                      }}
                      onError={setError}
                    />
                  </details>
                )}
              {loading ? (
                <div className="loading" role="status">
                  <span />
                  Cargando información…
                </div>
              ) : view === "dashboard" ? (
                <Dashboard stats={stats} go={go} />
              ) : ["clients", "proposals", "analysis"].includes(view) ? (
                <RecordsList
                  view={view}
                  filtered={filtered}
                  query={query}
                  setQuery={setQuery}
                  status={status}
                  setStatus={setStatus}
                  detail={detail}
                />
              ) : view === "admin" ? (
                <Administration onError={setError} />
              ) : view === "audit" ? (
                <AuditTable data={data} />
              ) : view === "reports" ? (
                <ReportsPanel data={data} reportFilters={reportFilters} />
              ) : view === "notifications" ? (
                <Card title="Tu actividad reciente">
                  {rows(data).length ? (
                    rows(data).map((n) => (
                      <div className="notification-row" key={n.id}>
                        <Bell size={19} />
                        <div>
                          <strong>{n.title}</strong>
                          <p>{n.message || n.body}</p>
                          <small>{date(n.created_at)}</small>
                        </div>
                      </div>
                    ))
                  ) : (
                    <Empty
                      title="Estás al día"
                      description="Las novedades de tus expedientes aparecerán aquí."
                    />
                  )}
                </Card>
              ) : (
                <Card title="Información de tu cuenta">
                  <dl className="details">
                    <div>
                      <dt>Nombre</dt>
                      <dd>{user.name}</dd>
                    </div>
                    <div>
                      <dt>Correo electrónico</dt>
                      <dd>{user.email}</dd>
                    </div>
                    <div>
                      <dt>Acceso</dt>
                      <dd>
                        {clientPortal ? "Portal del cliente" : "Equipo interno"}
                      </dd>
                    </div>
                  </dl>
                  <button
                    className="danger"
                    onClick={async () => {
                      await api("/auth/logout", { method: "POST" });
                      setUser(null);
                      setData(null);
                    }}
                  >
                    <LogOut size={16} />
                    Cerrar sesión
                  </button>
                </Card>
              )}
            </>
          )}
          <footer>
            WorkFlow Créditos <span>Gestión empresarial con trazabilidad</span>
            <ShieldCheck size={13} />
          </footer>
        </main>
      </div>
      <RecordFormModal
        modal={modal}
        setModal={setModal}
        create={create}
        profiles={profiles}
        directory={directory}
        user={user}
        selected={selected}
        clients={clients}
        catalog={catalog}
        error={error}
        busy={busy}
      />
    </div>
  );
}
