/**
 * Map library provider.
 *
 * Abstracts the dynamic import of the GL library so BaseMap doesn't
 * know or care whether it's MapLibre, Mapbox, or any future fork.
 *
 * To switch GL libraries:
 *   1. Install the new package.
 *   2. Change the import path below.
 *   3. Update the CSS import in layout.tsx.
 *   4. Update CSS class prefixes in globals.css.
 */

/**
 * Dynamically imports the map GL library.
 * Must be called client-side only (inside useEffect or event handlers).
 *
 * @returns The default export of the GL library (maplibregl namespace)
 */
export async function loadMapLibrary(): Promise<any> {
  const lib = await import('maplibre-gl')
  return lib.default
}

/** CSS class prefix used by the current GL library (for DOM queries) */
export const MAP_GL_CSS_PREFIX = 'maplibregl'
