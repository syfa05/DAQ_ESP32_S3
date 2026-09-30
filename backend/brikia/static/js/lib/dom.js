// Construction DOM sûre : tout texte passe par textContent / createTextNode
// (jamais innerHTML), donc aucune donnée serveur ne peut injecter du HTML.
const SVG_NS = 'http://www.w3.org/2000/svg';

function append(node, children) {
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    node.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
}

function applyProps(node, props) {
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') node.setAttribute('class', v);
    else if (k === 'dataset') Object.assign(node.dataset, v);
    else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'value') node.value = v;
    else node.setAttribute(k, v === true ? '' : v);
  }
}

export function h(tag, props, ...children) {
  const node = document.createElement(tag);
  applyProps(node, props);
  append(node, children);
  return node;
}

export function svg(tag, props, ...children) {
  const node = document.createElementNS(SVG_NS, tag);
  applyProps(node, props);
  append(node, children);
  return node;
}

export function replace(node, ...children) {
  node.replaceChildren();
  append(node, children);
  return node;
}

export const $ = (sel, root = document) => root.querySelector(sel);
