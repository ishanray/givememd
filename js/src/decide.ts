/** Is a fetched page real content, a bot wall, or an empty JS shell? (port of decide.py, heuristic only;
 * the Python version can also ask TypeSafe's Jev about unclear pages.) */
import { body, css, parse, remove, text } from './dom.js';

export const OK = 'ok', BLOCKED = 'blocked', NEEDS_JS = 'needs_js';
export type Label = typeof OK | typeof BLOCKED | typeof NEEDS_JS;

const CHALLENGE = new RegExp([
  'awsWafCookieDomainList', 'gokuProps',                          // AWS WAF
  'captcha-delivery\\.com', "var dd=\\{'rt'",                     // DataDome
  'cf-chl-', 'challenge-platform', '<title>Just a moment',        // Cloudflare
  'px-captcha', '_pxAppId',                                       // PerimeterX / HUMAN
  '/errors/validateCaptcha', 'Robot Check',                       // Amazon captcha
  'Click the button below to continue shopping',                  // Amazon soft block
  "You've been blocked by network security",                      // Reddit
  'Please enable JS and disable any ad blocker',
  'Access Denied</title>', '<title>Attention Required',
].join('|'), 'i');
const JS_SHELL = /enable javascript|javascript is (disabled|required)|you need to enable javascript/i;
const LOGIN_FORM = /<input[^>]+type=["']?password/i;
export const LOGIN_TEXT = /\b(log ?in|sign ?in|sign ?up|create an account)\b/i;
export const LOGIN_URL = /\/(accounts\/)?(login|signin|sign-in|authwall|checkpoint)\b/i;
const SHORT = 3000;

export function visibleText(html: string): string {
  const doc = parse(html);
  for (const n of css(doc, 'script,style,noscript,template,svg')) remove(n);
  const b = body(doc);
  return (b ? text(b, ' ') : '').replace(/\s+/gu, ' ').trim();
}

/** -> [label, reason, confident]. Not confident = short page with no vendor marker and no blocking status. */
export function heuristicStatus(html: string, status = 200): [Label, string, boolean] {
  if (!html) return [BLOCKED, `empty body (HTTP ${status})`, true];
  const head = html.slice(0, 200_000);
  const m = head.match(CHALLENGE);
  const t = visibleText(html);
  if (m && t.length < SHORT) return [BLOCKED, `challenge page (${m[0].slice(0, 40)})`, true];
  if ([401, 403, 429, 503].includes(status) && t.length < SHORT) return [BLOCKED, `HTTP ${status}`, true];
  if (t.length < SHORT && (LOGIN_FORM.test(head) || /\bpassword\b/i.test(t.slice(0, 1500))) && LOGIN_TEXT.test(t.slice(0, 1500)))
    return [BLOCKED, 'login wall', true];
  if (t.length >= SHORT) return [OK, `${t.length} chars of text`, true];
  if (t.length < 400) {
    const scripts = html.split('<script').length - 1;
    if (JS_SHELL.test(t) || scripts >= 3 || (scripts >= 1 && t.length < 100)) return [NEEDS_JS, `${t.length} chars of text, ${scripts} scripts`, false];
    if (t.length < 100) return [BLOCKED, `only ${t.length} chars of text`, false];
  }
  return [OK, `${t.length} chars of text`, false];
}

export function pageStatus(html: string, status = 200): [Label, string] {
  const [label, why] = heuristicStatus(html, status);
  return [label, why];
}
