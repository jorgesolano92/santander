import { importLibrary, setOptions } from '@googlemaps/js-api-loader';

let loadPromise: Promise<typeof google> | null = null;
let optionsConfigured = false;

export function getGoogleMapsApiKey(): string {
  return (import.meta.env.VITE_GOOGLE_MAPS_API_KEY as string | undefined)?.trim() ?? '';
}

function configureLoader(apiKey: string) {
  if (optionsConfigured) return;
  setOptions({ key: apiKey, v: 'weekly' });
  optionsConfigured = true;
}

/** Carga maps + marker con la API funcional del js-api-loader v2. */
export function loadGoogleMaps(): Promise<typeof google> {
  const apiKey = getGoogleMapsApiKey();
  if (!apiKey) {
    return Promise.reject(
      new Error('Falta VITE_GOOGLE_MAPS_API_KEY en coce-dashboard/.env'),
    );
  }

  if (!loadPromise) {
    configureLoader(apiKey);
    loadPromise = Promise.all([importLibrary('maps'), importLibrary('marker')])
      .then(() => {
        if (typeof google === 'undefined' || !google.maps) {
          throw new Error('Google Maps no quedó disponible tras importLibrary');
        }
        return google;
      })
      .catch((err) => {
        loadPromise = null;
        throw err;
      });
  }

  return loadPromise;
}

export function hasMapCoords(
  location?: { latitude?: number | null; longitude?: number | null },
): boolean {
  if (!location) return false;
  const { latitude: lat, longitude: lng } = location;
  return (
    lat != null &&
    lng != null &&
    !Number.isNaN(Number(lat)) &&
    !Number.isNaN(Number(lng))
  );
}
