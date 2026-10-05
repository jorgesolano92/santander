export function GlobalLoader({
  open,
  message = "Cargando...",
  logoSrc = "/assets/invia-board-logo.png",
  logoFallback = "/assets/invia-board-logo.png",
}) {
  if (!open) return null;

  return (
    <>
      <style>
        {`
          @keyframes template-loader-pulse {
            0%, 100% { transform: scale(1); opacity: 0.92; }
            50% { transform: scale(1.08); opacity: 1; }
          }
        `}
      </style>

      <div
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 9999,
          background: "rgba(17, 24, 39, 0.26)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          backdropFilter: "blur(1px)",
        }}
      >
        <div
          style={{
            position: "relative",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 16,
            padding: "30px 44px",
            minWidth: 280,
            borderRadius: 18,
            background: "rgba(255,255,255,0.9)",
            border: "1px solid rgba(224,224,224,0.9)",
            boxShadow: "0 10px 35px rgba(0,0,0,0.12)",
          }}
        >
          <div
            style={{
              position: "relative",
              width: 92,
              height: 92,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <img
              src={logoSrc || logoFallback}
              alt="Cargando"
              style={{
                width: 80,
                height: 80,
                objectFit: "contain",
                animation: "template-loader-pulse 1.1s ease-in-out infinite",
                zIndex: 1,
              }}
              onError={(e) => {
                if (e.currentTarget.src !== logoFallback) {
                  e.currentTarget.src = logoFallback;
                }
              }}
            />
          </div>
          <div style={{ fontSize: 14, fontWeight: 700, color: "#374151" }}>
            {message}
          </div>
        </div>
      </div>
    </>
  );
}
