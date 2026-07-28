export function TopNavbar({
  title = "Control de Accesos",
  tabs = [],
  activeTab = 0,
  onTabChange = () => {},
  connectionLabel = "Conexión estable",
  userLabel = "Usuario",
  logoSrc = "/assets/logo.png",
  primaryColor = "#E50914",
  primaryDarkColor = "#B20710",
  rightSlot = null,
}) {
  return (
    <div
      className="h-15 flex items-center justify-between px-6 text-white"
      style={{
        position: "sticky",
        top: 0,
        zIndex: 100,
        background: `linear-gradient(90deg, ${primaryColor} 0%, ${primaryDarkColor} 100%)`,
      }}
    >
      <div className="flex items-center gap-10">
        <img
          src={logoSrc}
          alt="Logo"
          className="w-30 h-auto"
          onError={(e) => {
            e.currentTarget.src = "/assets/logo.png";
          }}
        />

        <nav className="flex gap-4 text-sm pt-3.5">
          {tabs.map((tabName, idx) => (
            <button
              key={tabName}
              type="button"
              onClick={() => onTabChange(idx)}
              className="cursor-pointer justify-between"
            >
              {tabName}
              <div
                className={
                  activeTab === idx
                    ? "font-semibold bg-white h-1 w-full rounded-full"
                    : "opacity-80 hover:opacity-100"
                }
              ></div>
            </button>
          ))}
          <div className="border-b-2 border-white pb-3.5"></div>
        </nav>
      </div>

      {rightSlot ? (
        <div className="flex items-center gap-3" style={{ position: "relative", overflow: "visible" }}>
          {rightSlot}
        </div>
      ) : null}

      {/* <div className="flex items-center gap-4 text-sm">
        <span className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-green-400"></span>
          {connectionLabel}
        </span>

        <span className="opacity-90">{userLabel}</span>
      </div> */}
    </div>
  );
}
