/*
  cl_live.js — minimal client for oTree live_method pages.

  The page template renders <script id="cl-live" data-path="..."> with
  oTree's own socket path (view.live_url()), so messages reach the page's
  live_method. Exposes:

    clLive.send(obj)        queue + send (delivered once the socket opens)
    clLive.onMessage(fn)    fn(payload) for every message from the server
    clLive.isOpen()         true while connected

  Messages sent before the socket opens are queued, and the socket
  reconnects if it drops, so nothing is silently lost on a slow network.
*/
(function () {
  var tag = document.getElementById('cl-live');
  var path = tag && tag.dataset ? tag.dataset.path : null;
  var queue = [];
  var handlers = [];
  var ws = null;
  var closing = false;

  function flush() {
    while (queue.length && ws && ws.readyState === 1) {
      ws.send(JSON.stringify(queue.shift()));
    }
  }

  function connect() {
    if (!path) return;
    var scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    try {
      ws = new WebSocket(scheme + '://' + window.location.host + path);
    } catch (e) {
      setTimeout(connect, 1500);
      return;
    }
    ws.onopen = flush;
    ws.onmessage = function (e) {
      var data;
      try { data = JSON.parse(e.data); } catch (err) { return; }
      handlers.forEach(function (fn) { fn(data); });
    };
    ws.onclose = function () {
      if (!closing) setTimeout(connect, 1500);
    };
  }

  window.addEventListener('beforeunload', function () { closing = true; });

  window.clLive = {
    available: !!path,
    send: function (msg) { queue.push(msg); flush(); },
    onMessage: function (fn) { handlers.push(fn); },
    isOpen: function () { return !!(ws && ws.readyState === 1); }
  };

  connect();
})();
