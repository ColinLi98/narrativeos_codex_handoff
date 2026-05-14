// Reader v2 shell DOM registry. Keeps the new shell isolated from legacy Reader DOM.

var ReaderShellV2DOM = (() => ({
  root: DOMShared.query("#reader-shell-v2"),
  title: DOMShared.query("#reader-shell-v2-title"),
  copy: DOMShared.query("#reader-shell-v2-copy"),
  status: DOMShared.query("#reader-shell-v2-status"),
  body: DOMShared.query("#reader-shell-v2-body"),
}))();
