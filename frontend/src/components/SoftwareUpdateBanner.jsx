import { useCallback, useEffect, useState } from "react";

/**
 * Banner de actualización remota COCE (panel PC o APK Akuvox).
 */
export function SoftwareUpdateBanner({ apiFetch }) {
  const [pending, setPending] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [info, setInfo] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const data = await apiFetch("/software-update");
      setPending(data?.pending || null);
    } catch {
      /* ignore */
    }
  }, [apiFetch]);

  useEffect(() => {
    void refresh();
    const onAvail = () => void refresh();
    window.addEventListener("software_update_available", onAvail);
    const iv = setInterval(() => void refresh(), 60000);
    return () => {
      window.removeEventListener("software_update_available", onAvail);
      clearInterval(iv);
    };
  }, [refresh]);

  if (!pending?.kind) return null;

  const isApk = pending.kind === "tablet_apk";
  const title = isApk
    ? `Nueva APK tablet ${pending.version}`
    : `Actualización panel ${pending.version}`;

  const onApply = async () => {
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      if (isApk) {
        const filename = `tablet-${pending.version}.apk`;
        const link = document.createElement("a");
        link.href = `/api/panel/software-update/apk`;
        link.download = filename;
        link.rel = "noopener";
        document.body.appendChild(link);
        link.click();
        link.remove();
        setInfo("Descarga iniciada. Revisa la barra de descargas del navegador.");
        try {
          await apiFetch("/software-update/dismiss", { method: "POST" });
        } catch {
          /* La descarga ya está en curso; no bloquear la UI si falla el dismiss. */
        }
        setPending(null);
      } else {
        await apiFetch("/software-update/apply", { method: "POST" });
        setPending(null);
        window.alert(
          "Actualización aplicada. Reinicia el servicio del panel para cargar el nuevo código.",
        );
      }
    } catch (e) {
      setError(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  };

  const onDismiss = async () => {
    try {
      await apiFetch("/software-update/dismiss", { method: "POST" });
      setPending(null);
    } catch (e) {
      setError(e?.message || String(e));
    }
  };

  return (
    <div
      style={{
        background: isApk ? "#1e3a5f" : "#3f2a1a",
        color: "#fff",
        padding: "10px 16px",
        display: "flex",
        alignItems: "center",
        gap: 12,
        flexWrap: "wrap",
        borderBottom: "1px solid rgba(255,255,255,0.15)",
      }}
    >
      <strong style={{ flex: 1, minWidth: 200 }}>{title}</strong>
      {pending.changelog ? (
        <span style={{ opacity: 0.85, fontSize: 13 }}>{pending.changelog}</span>
      ) : null}
      {info ? <span style={{ opacity: 0.85, fontSize: 13 }}>{info}</span> : null}
      {error ? <span style={{ color: "#fecaca", fontSize: 13 }}>{error}</span> : null}
      <button
        type="button"
        disabled={busy}
        onClick={() => void onApply()}
        style={{
          background: "#fff",
          color: "#111",
          border: 0,
          borderRadius: 8,
          padding: "8px 14px",
          fontWeight: 700,
          cursor: "pointer",
        }}
      >
        {busy ? "…" : isApk ? "Descargar APK" : "Actualizar panel"}
      </button>
      <button
        type="button"
        disabled={busy}
        onClick={() => void onDismiss()}
        style={{
          background: "transparent",
          color: "#fff",
          border: "1px solid rgba(255,255,255,0.4)",
          borderRadius: 8,
          padding: "8px 12px",
          cursor: "pointer",
        }}
      >
        Más tarde
      </button>
    </div>
  );
}
