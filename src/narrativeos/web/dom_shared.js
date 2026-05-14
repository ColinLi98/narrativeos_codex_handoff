// Shared DOM query helpers so each domain-specific DOM runtime can produce safe nodes directly.

var DOMShared = (() => {
  const NULL_NODE = {
    innerHTML: "",
    textContent: "",
    value: "",
    checked: false,
    disabled: false,
    dataset: {},
    style: {},
    classList: {
      add() {},
      remove() {},
      toggle() { return false; },
      contains() { return false; },
    },
    addEventListener() {},
    appendChild() {},
    prepend() {},
    remove() {},
    scrollIntoView() {},
    setAttribute() {},
    removeAttribute() {},
    focus() {},
    blur() {},
    querySelector() { return NULL_NODE; },
    querySelectorAll() { return []; },
    closest() { return null; },
  };

  function query(selector) {
    return document.querySelector(selector) || NULL_NODE;
  }

  function queryAll(selector) {
    return [...document.querySelectorAll(selector)];
  }

  return {
    NULL_NODE,
    query,
    queryAll,
  };
})();
