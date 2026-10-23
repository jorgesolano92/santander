import { useState, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import { getPanelToken, setPanelToken } from "./panelAuth";

export default function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [confirmSave, setConfirmSave] = useState(false);
  const [needsFirstUser, setNeedsFirstUser] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    if (getPanelToken()) {
      navigate("/", { replace: true });
    }
  }, [navigate]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/auth/setup-status");
        const data = await res.json().catch(() => ({}));
        if (!cancelled) {
          setNeedsFirstUser(Boolean(data.needs_first_user));
        }
      } catch {
        if (!cancelled) setNeedsFirstUser(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function loginWith(user, pass) {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: user.trim(),
        password: pass,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(
        typeof data.detail === "string"
          ? data.detail
          : "No se pudo iniciar sesión",
      );
    }
    if (!data.access_token) {
      throw new Error("Respuesta inválida del servidor");
    }
    setPanelToken(data.access_token);
    navigate("/", { replace: true });
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    const user = username.trim();
    try {
      if (needsFirstUser) {
        if (password !== password2) {
          setError("Las contraseñas no coinciden");
          return;
        }
        if (!confirmSave) {
          setError("Debes confirmar que los datos son correctos");
          return;
        }
        const reg = await fetch("/api/auth/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username: user, password }),
        });
        const regData = await reg.json().catch(() => ({}));
        if (!reg.ok) {
          throw new Error(
            typeof regData.detail === "string"
              ? regData.detail
              : "No se pudo crear el usuario",
          );
        }
        await loginWith(user, password);
        return;
      }
      await loginWith(user, password);
    } catch (err) {
      const msg =
        err instanceof Error && err.message ? err.message : "Error de red";
      setError(msg === "Failed to fetch" ? "Error de red" : msg);
    } finally {
      setLoading(false);
    }
  }

  const bootstrapping = needsFirstUser === true;

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-[#F5F5F5] px-4">
      <div className="w-full max-w-md rounded-2xl border border-[#E0E0E0] bg-white p-8 shadow-sm">
        <h1 className="text-xl font-semibold text-[#111827] mb-1">
          Control de accesos
        </h1>
        <p className="text-sm text-[#6B7280] mb-6">
          {bootstrapping
            ? "Primer acceso: crea el usuario administrador del panel"
            : "Inicia sesión para abrir el panel"}
        </p>
        {bootstrapping ? (
          <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 leading-relaxed">
            No hay usuarios en esta instalación. El usuario y la contraseña que
            indiques se guardarán de forma segura (hash) en la base de datos
            local del panel. Guárdalos: harán falta para entrar después.
          </div>
        ) : null}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="login-user"
              className="block text-xs font-medium text-[#374151] mb-1"
            >
              Usuario
            </label>
            <input
              id="login-user"
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded-lg border border-[#E5E7EB] px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-red-600/25 focus:border-red-600"
              required
              minLength={3}
            />
          </div>
          <div>
            <label
              htmlFor="login-pass"
              className="block text-xs font-medium text-[#374151] mb-1"
            >
              Contraseña
            </label>
            <input
              id="login-pass"
              type="password"
              autoComplete={bootstrapping ? "new-password" : "current-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-[#E5E7EB] px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-red-600/25 focus:border-red-600"
              required
              minLength={8}
            />
          </div>
          {bootstrapping ? (
            <>
              <div>
                <label
                  htmlFor="login-pass2"
                  className="block text-xs font-medium text-[#374151] mb-1"
                >
                  Repetir contraseña
                </label>
                <input
                  id="login-pass2"
                  type="password"
                  autoComplete="new-password"
                  value={password2}
                  onChange={(e) => setPassword2(e.target.value)}
                  className="w-full rounded-lg border border-[#E5E7EB] px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-red-600/25 focus:border-red-600"
                  required
                  minLength={8}
                />
              </div>
              <label className="flex items-start gap-2 text-xs text-[#374151] cursor-pointer">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={confirmSave}
                  onChange={(e) => setConfirmSave(e.target.checked)}
                  required
                />
                <span>
                  Confirmo que el usuario y la contraseña son correctos y que se
                  guardarán en esta instalación como acceso al panel.
                </span>
              </label>
            </>
          ) : null}
          {error ? (
            <p className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
              {error}
            </p>
          ) : null}
          <button
            type="submit"
            disabled={loading || needsFirstUser === null}
            className="w-full rounded-lg bg-[#E50914] hover:bg-[#B20710] text-white text-sm font-semibold py-2.5 disabled:opacity-50 transition-colors"
          >
            {loading
              ? bootstrapping
                ? "Creando usuario…"
                : "Entrando…"
              : bootstrapping
                ? "Crear usuario y entrar"
                : "Entrar"}
          </button>
        </form>
        <p className="mt-6 text-center text-xs text-[#9CA3AF]">
          <Link to="/" className="text-[#6B7280] hover:text-[#111827]">
            Volver al inicio
          </Link>
        </p>
      </div>
    </div>
  );
}
