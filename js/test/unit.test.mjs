import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { convert, pageStatus, normalize, UnsafeURL } from '../dist/index.js';
import { isPublicIp, checkPublic, decode, metadataChars, systemBrowser, installHeadlessShell } from '../dist/fetch.js';
import { cleanUrl } from '../dist/extract.js';

const fx = (n) => readFileSync(new URL(`../../tests/fixtures/${n}`, import.meta.url), 'utf8');
const filler = (s, n) => s.repeat(n);

test('tracking params are stripped from links', () => {
  assert.equal(cleanUrl('/dp/B0D1XD1ZV3/ref=sr_1_1?pd_rd_w=abc&content-id=x&utm_source=y&keywords=airpods', 'https://www.amazon.com/'),
    'https://www.amazon.com/dp/B0D1XD1ZV3?keywords=airpods');
  assert.equal(cleanUrl('javascript:void(0)', 'https://a.com'), null);
});

test('bot walls are detected', () => {
  for (const f of ['block_aws_waf.html', 'block_shop_interstitial.html', 'block_datadome.html', 'block_network_security.html'])
    assert.notEqual(pageStatus(fx(f), 200)[0], 'ok', f);
  for (const f of ['ok_docs.html', 'ok_listings.html', 'ok_tiny_static.html']) assert.equal(pageStatus(fx(f), 200)[0], 'ok', f);
});

test('login pages are blocked', () => {
  const html = '<html><body><h2>Log into Instagram</h2><form><input name="u"><input type="password"></form></body></html>';
  assert.equal(pageStatus(html, 200)[0], 'blocked');
});

test('embedded listings become one table, in place of the rendered grid', () => {
  const md = convert(fx('ok_listings.html'), 'https://homes.example/', { links: false });
  assert.match(md, /## Data \(41 records\)/);
  assert.equal(md.split('101 Maple Ave').length - 1, 1);
  assert.ok(md.indexOf('## Data') < md.indexOf('Browse homes') || md.includes('## Data'));
});

test('collapsed see-more content kept, modals dropped', () => {
  const md = convert('<main><div class="a-expander-content" style="display:none"><p>Battery lasts 30 hours with case</p></div>' +
    '<div class="modal" style="display:none"><p>Sign in to continue</p></div><p>Main product text here</p></main>', 'https://x.com');
  assert.ok(md.includes('Battery lasts 30 hours') && !md.includes('Sign in to continue'));
});

test('react streamed segments are moved into place', () => {
  const html = '<html><body><main><h1>News</h1><template id="B:0"></template><p>Loading…</p><div hidden id="S:0"><p>' +
    filler('The streamed story text arrives late. ', 10) + '</p></div><script>$RC("B:0","S:0")</script></main></body></html>';
  const md = convert(html, 'https://x.com', { links: false });
  assert.ok(md.includes('streamed story text arrives late') && md.indexOf('# News') < md.indexOf('streamed story'));
});

test('story cards keep headlines, menus are dropped', () => {
  const menu = '<ul>' + Array.from({ length: 8 }, (_, i) => `<li><a href="/m${i}">Menu ${i}</a></li>`).join('') + '</ul>';
  const cards = '<div>' + Array.from({ length: 8 }, (_, i) => `<a href="/s${i}">Council approves the new river bridge plan ${i}</a>`).join('') + '</div>';
  const md = convert(`<main><p>${filler('Front page intro text. ', 30)}</p>${menu}${cards}</main>`, 'https://news.example', { links: false });
  assert.ok(md.includes('Council approves the new river bridge plan 3 · Council approves the new river bridge plan 4'));
  assert.ok(!md.includes('Menu 3'));
});

test('portal pages keep their link lists', () => {
  const menus = Array.from({ length: 6 }, (_, i) => '<ul>' + Array.from({ length: 8 }, (_, j) => `<li><a href="/s${i}${j}">Story headline number ${i}${j} about events</a></li>`).join('') + '</ul>').join('');
  assert.ok(convert(`<html><body><main>${menus}<p>Short intro.</p></main></body></html>`, 'https://portal.example', { links: false }).includes('Story headline number 37 about events'));
});

test('non-Latin text survives de-duplication', () => {
  const md = convert('<main><p>' + filler('東京の天気は晴れです。明日も晴れるでしょう。', 30) + '</p><p>ニュース速報：新しい駅が開業しました。</p></main>', 'https://jp.example', { links: false });
  assert.ok(md.includes('ニュース速報'));
});

test('comments add no space', () => {
  const md = convert('<main><p>' + filler('Nutrition per serving: fat 29<!-- -->g, carbs 59<!-- -->g. ', 12) + '</p></main>', 'https://x.com', { links: false });
  assert.ok(md.includes('fat 29g') && !md.includes('29 g'));
});

test('no space before punctuation after inline elements', () => {
  const md = convert('<main><h2>Title <em>here</em>!</h2><p>' + filler('It was <em>already validated it</em>. See <a href="/r">the report</a>, and (<a href="/l">Linux</a>) and <a href="/v">Vercel</a>\'s team. <span>A</span><span>B</span>. ', 12) + '</p><table><tr><th>Date</th><th>Event</th></tr><tr><td>Oct 7</td><td>accepted into <code>net.git</code>.</td></tr></table><ul><li><a href="/c"><code>fix</code> (<code>abc123</code>)</a></li></ul></main>', 'https://x.com', { links: false });
  for (const s of ['validated it.', 'the report,', '(Linux)', "Vercel's", 'A B.', '## Title here!', 'net.git.', 'fix (abc123)']) assert.ok(md.includes(s), s);
  assert.ok(!md.includes(' .') && !md.includes(' ,'));
});

test('deep nesting does not crash', () => {
  const html = '<main>' + '<span>'.repeat(3000) + 'deep text here' + '</span>'.repeat(3000) + '<p>' + filler('body ', 100) + '</p></main>';
  assert.ok(convert(html, 'https://x.com', { links: false }).includes('deep text here'));
});

test('non-UTF-8 pages decode', () => {
  assert.ok(decode(Buffer.from('<p>Москва</p>', 'latin1').length ? new Uint8Array([0xcc, 0xee, 0xf1, 0xea, 0xe2, 0xe0]) : null, 'text/html; charset=windows-1251').includes('Москва'));
});

test('generic login metadata is not a partial result', () => {
  assert.equal(metadataChars('<meta name="description" content="Create an account or log in to Instagram - Share what you\'re into.">'), 0);
  assert.ok(metadataChars('<meta name="description" content="104M Followers, 94 Following, 4,986 Posts - NASA (@nasa) on Instagram">') > 0);
});

test('address classification', () => {
  for (const ip of ['104.20.23.154', '8.8.8.8', '2606:4700::6810:1', '::ffff:8.8.8.8']) assert.ok(isPublicIp(ip), ip);
  for (const ip of ['127.0.0.1', '10.1.2.3', '192.168.1.1', '169.254.169.254', '100.64.0.1', '0.0.0.0', '::1', 'fe80::1', 'fd00::1', '::ffff:127.0.0.1', '224.0.0.1'])
    assert.ok(!isPublicIp(ip), ip);
});

test('private targets, odd ports and non-http schemes are refused', async () => {
  for (const t of ['http://127.0.0.1/', 'http://localhost:8080/admin', 'http://169.254.169.254/latest/', 'http://10.0.0.1/', 'http://[::1]/'])
    await assert.rejects(checkPublic(normalize(t)), UnsafeURL, t);
  await assert.rejects(checkPublic(normalize('http://example.com:6379/')), UnsafeURL);
  for (const t of ['file:///etc/passwd', 'ftp://example.com/x']) assert.throws(() => normalize(t), UnsafeURL);
  assert.equal(normalize('/amazon.com/dp/B0D1XD1ZV3'), 'https://amazon.com/dp/B0D1XD1ZV3');
});

test('system browser: env first, then installed paths', () => {
  process.env.GIVEMEMD_CHROME = '/opt/my/chrome';
  assert.equal(systemBrowser(), '/opt/my/chrome');
  delete process.env.GIVEMEMD_CHROME;
  assert.equal(systemBrowser([process.execPath]), process.execPath);   // any existing file stands in for a browser
  assert.equal(systemBrowser(['/nonexistent/chrome']), null);
});

test('browser download can be disabled', () => {
  process.env.GIVEMEMD_NO_BROWSER_DOWNLOAD = '1';
  try { assert.throws(() => installHeadlessShell(), /GIVEMEMD_NO_BROWSER_DOWNLOAD/); }
  finally { delete process.env.GIVEMEMD_NO_BROWSER_DOWNLOAD; }
});

test('image-only structured data is not summarized or tabled', () => {
  const html = '<html><head><script type="application/ld+json">[{"@context": "https://schema.org", "@type": "BlogPosting", "headline": "Sandbox engine", "datePublished": "2026-11-04"}, {"@type": "ImageObject", "url": "https://x.com/i0.png", "caption": "Ada", "width": 512, "height": 512}, {"@type": "ImageObject", "url": "https://x.com/i1.png", "caption": "Bo", "width": 535, "height": 535}, {"@type": "ImageObject", "url": "https://x.com/i2.png", "caption": "Cy", "width": 500, "height": 500}, {"@type": "ImageObject", "url": "https://x.com/i3.png", "caption": "Hero image", "width": 1920, "height": 1920}, {"@type": "Person", "name": "Ada Lee", "jobTitle": "CTO"}, {"@type": "Person", "name": "Bo Kim", "jobTitle": "Engineer"}, {"@type": "Person", "name": "Cy Diaz", "jobTitle": "Engineer"}]</script></head>'
    + '<body><main><h1>Sandbox engine</h1><p>' + filler('MicroVMs isolate each sandbox. ', 20) + '</p></main></body></html>';
  const md = convert(html, 'https://x.com/post', { links: false });
  assert.ok(!md.includes('ImageObject') && !md.includes('| width') && !md.includes('1920'));
  assert.ok(md.includes('Person (3): Ada Lee; Bo Kim; Cy Diaz'));
});
