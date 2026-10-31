/** Small helpers that keep behaviour identical to the Python implementation. */

/** Python's re \s+ -> ' ' and strip. */
export const ws = (s: string): string => s.replace(/\s+/gu, ' ').trim();

/** Python's re.sub(r'[\W_]+', '', s.lower()) with Unicode semantics (JS \W is ASCII-only). */
export const alnumKey = (s: string): string => s.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '');
/** Python's re.sub(r'\W+', ' ', s.lower()).strip() with Unicode semantics. */
export const wordKey = (s: string): string => s.toLowerCase().replace(/[^\p{L}\p{N}_]+/gu, ' ').trim();

/** Python str() for JSON scalars (strings, numbers). Floats with an integer value print as '2' here vs '2.0' in
 * Python: JSON.parse cannot tell them apart. */
export const pyStr = (v: unknown): string => (typeof v === 'string' ? v : typeof v === 'number' ? String(v) : String(v));

export const isScalar = (v: unknown): v is string | number => typeof v === 'string' || (typeof v === 'number' && Number.isFinite(v));
export const isDict = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);

/** json.dumps(x, sort_keys=True, default=str) equivalent, for signatures. */
export function stableStringify(x: unknown): string {
  if (Array.isArray(x)) return '[' + x.map(stableStringify).join(', ') + ']';
  if (isDict(x)) return '{' + Object.keys(x).sort().map((k) => JSON.stringify(k) + ': ' + stableStringify(x[k])).join(', ') + '}';
  return JSON.stringify(x) ?? 'null';
}

/** Ordered unique (dict.fromkeys). */
export const uniq = <T>(xs: Iterable<T>): T[] => [...new Set(xs)];
