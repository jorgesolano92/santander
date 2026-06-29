function canalParam(canal) {
  if (canal == null || canal === "") return "";
  const ch =
    typeof canal === "number" ? `p${canal}` : String(canal).toLowerCase();
  return `?canal=${encodeURIComponent(ch)}`;
}

export function createZaguanDeviceApi(apiFetchZaguan) {
  return {
    ping: (canal) =>
      apiFetchZaguan(`/api/zaguan/device/ping${canalParam(canal)}`),
    pingAll: () => apiFetchZaguan("/api/zaguan/device/ping-all"),
    getEstado: (canal) =>
      apiFetchZaguan(`/api/zaguan/device/estado${canalParam(canal)}`),
    getConfig: (canal) =>
      apiFetchZaguan(`/api/zaguan/device/config${canalParam(canal)}`),
    getOtaVersion: (canal) =>
      apiFetchZaguan(`/api/zaguan/device/ota/version${canalParam(canal)}`),
    getTarget: () => apiFetchZaguan("/api/zaguan/device/target"),
    saveTarget: (target) =>
      apiFetchZaguan("/api/zaguan/device/target", {
        method: "POST",
        body: JSON.stringify(target),
      }),
    setEstado: (canal, estado) =>
      apiFetchZaguan(`/api/zaguan/device/canal/p${canal}/estado`, {
        method: "POST",
        body: JSON.stringify({ estado }),
      }),
    configRed: (payload, canal) =>
      apiFetchZaguan(`/api/zaguan/device/config/red${canalParam(canal)}`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    configCanal: (payload, canal) =>
      apiFetchZaguan(`/api/zaguan/device/config/canal${canalParam(canal)}`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    configEstado: (payload, canal) =>
      apiFetchZaguan(`/api/zaguan/device/config/estado${canalParam(canal)}`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    configFlash: (payload, canal) =>
      apiFetchZaguan(`/api/zaguan/device/config/flash${canalParam(canal)}`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
  };
}
