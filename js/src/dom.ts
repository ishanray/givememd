/** A thin DOM layer with the operations the extractor needs (mirrors the selectolax calls in the Python version).
 * Parsing is parse5 (spec-compliant HTML5, like lexbor), producing domhandler nodes; css-select does selectors. */
import { selectAll, selectOne } from 'css-select';
import { Document, Element, Text, type AnyNode, type ParentNode } from 'domhandler';
import { removeElement, replaceElement } from 'domutils';
import { parse as parse5Parse } from 'parse5';
import { adapter } from 'parse5-htmlparser2-tree-adapter';

export type El = Element;
export type Node = AnyNode;

export function parse(html: string): Document {
  // scriptingEnabled: false parses <noscript> contents as elements (as lexbor does) instead of one raw-text node,
  // so page-size measurements match the Python version
  return parse5Parse(html, { treeAdapter: adapter, scriptingEnabled: false }) as unknown as Document;
}

export const isEl = (n: AnyNode | null | undefined): n is Element =>
  !!n && (n.type === 'tag' || n.type === 'script' || n.type === 'style');
export const isText = (n: AnyNode): n is Text => n.type === 'text';

/** All matching descendants, in document order. */
export function css(root: ParentNode, selector: string): Element[] {
  return selectAll(selector, root as never) as unknown as Element[];
}
export function cssFirst(root: ParentNode, selector: string): Element | null {
  return (selectOne(selector, root as never) as unknown as Element) ?? null;
}

/** Text of every text node under n, joined by sep (selectolax `text(separator=...)`). */
export function text(n: AnyNode, sep = ''): string {
  const out: string[] = [];
  const rec = (x: AnyNode) => {
    if (x.type === 'text') { out.push((x as Text).data); return; }
    const kids = (x as ParentNode).children;
    if (kids) for (const c of kids) rec(c);
  };
  rec(n);
  return out.join(sep);
}

export const tag = (n: AnyNode): string => (isEl(n) ? n.name.toLowerCase() : n.type === 'text' ? '-text' : '-other');
export const attr = (n: Element, name: string): string | undefined => n.attribs?.[name];
export const hasAttr = (n: Element, name: string): boolean => !!n.attribs && name in n.attribs;

export function remove(n: AnyNode): void {
  if (n.parent) removeElement(n);
}
export function replaceWithText(n: AnyNode, s: string): void {
  if (n.parent) replaceElement(n, new Text(s));
}
export function replaceWith(n: AnyNode, other: AnyNode): void {
  if (!n.parent) return;
  if (other.parent) removeElement(other);
  replaceElement(n, other);
}
/** Detached = removed from the tree (it or an ancestor no longer reaches the document). */
export function attached(n: AnyNode): boolean {
  let p: AnyNode | null = n;
  while (p) { if (p.type === 'root') return true; p = p.parent; }
  return false;
}
export function body(doc: Document): Element | null {
  return cssFirst(doc, 'body');
}
export const children = (n: ParentNode): AnyNode[] => n.children ?? [];
