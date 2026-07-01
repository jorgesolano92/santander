export const ESTADOS_VALIDOS = ["libre", "ocupado", "abriendo", "apagado"];

/** IP por defecto de cada ESP (canal lógico p1–p4). */
export const CANAL_DEFAULT_IPS = {
  1: "192.168.1.60",
  2: "192.168.1.62",
  3: "192.168.1.61",
  4: "192.168.1.63",
};

export const CANAL_INFO = {
  1: {
    corto: "C1",
    puerta: "P1",
    rol: "Videoportero",
    ubicacion: "Exterior",
    nombre: "P1 — videoportero exterior",
    ip: CANAL_DEFAULT_IPS[1],
    gpioLed: 2,
    gpioBtn: 15,
  },
  2: {
    corto: "C2",
    puerta: "P2",
    rol: "Videoportero",
    ubicacion: "Interior",
    nombre: "P2 — videoportero interior",
    ip: CANAL_DEFAULT_IPS[2],
    gpioLed: 4,
    gpioBtn: 16,
  },
  3: {
    corto: "C3",
    puerta: "P1",
    rol: "Pulsador",
    ubicacion: "Exterior",
    nombre: "P1 — pulsador interior",
    ip: CANAL_DEFAULT_IPS[3],
    gpioLed: 5,
    gpioBtn: 17,
  },
  4: {
    corto: "C4",
    puerta: "P2",
    rol: "Pulsador",
    ubicacion: "Interior",
    nombre: "P2 — pulsador interior",
    ip: CANAL_DEFAULT_IPS[4],
    gpioLed: 6,
    gpioBtn: 18,
  },
};

export const ESTADO_META = {
  libre: { label: "Libre", desc: "Se puede entrar" },
  ocupado: { label: "Ocupado", desc: "Esperar" },
  abriendo: { label: "Abriendo", desc: "Apertura en curso" },
  apagado: { label: "Apagado", desc: "Fuera de servicio" },
};

export const TWEAK_DEFAULTS = {
  tema: "claro",
  densidad: "normal",
  halo: true,
  intervaloPing: 10,
};

/** Parpadeo verde en libre durante ventana WinHose (debe coincidir con backend). */
export const WINHOSE_LIBRE_PARPADEO_MS = 1000;

export function withWinhoseParpadeo(canal, estado, baseCfg, winhoseParpadeo) {
  if (estado !== "libre" || !winhoseParpadeo?.[`p${canal}`]) {
    return baseCfg;
  }
  return {
    ...baseCfg,
    color: [0, 200, 0],
    animacion: "parpadeo",
    velocidad: WINHOSE_LIBRE_PARPADEO_MS,
  };
}

/** Canales p1–p4: simulación POST /api/zaguan/pulsacion/pN al orquestador. */
export const ZAGUAN_PULSADOR_CANALES = [
  {
    canal: 1,
    puerta: "P1 (calle)",
    dispositivo: "Videoportero exterior P1",
    ubicacion: "Exterior",
    led: "C1",
    ip: CANAL_DEFAULT_IPS[1],
    inModbus: "IN_02_08",
  },
  {
    canal: 2,
    puerta: "P2 (oficina)",
    dispositivo: "Videoportero interior P2",
    ubicacion: "Interior zaguán",
    led: "C2",
    ip: CANAL_DEFAULT_IPS[2],
    inModbus: "IN_03_08",
  },
  {
    canal: 3,
    puerta: "P1 (calle)",
    dispositivo: "Pulsador exterior P1",
    ubicacion: "Exterior",
    led: "C3",
    ip: CANAL_DEFAULT_IPS[3],
    inModbus: "IN_02_07",
  },
  {
    canal: 4,
    puerta: "P2 (oficina)",
    dispositivo: "Pulsador interior P2",
    ubicacion: "Interior zaguán",
    led: "C4",
    ip: CANAL_DEFAULT_IPS[4],
    inModbus: "IN_03_07",
  },
];

/** WinHose: inductivo llave echada (cerrado=ON, abierto=OFF → flanco ON→OFF). */
export const ZAGUAN_LLAVE_ECHADA = [
  {
    id: 1,
    label: "Llave echada 1",
    puerta: "P1 (calle)",
    code: "IN_02_03",
    placa: 2,
    canalIn: 3,
  },
  {
    id: 2,
    label: "Llave echada 2",
    puerta: "P2 (oficina)",
    code: "IN_03_03",
    placa: 3,
    canalIn: 3,
  },
];
