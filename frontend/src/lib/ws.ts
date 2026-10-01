// WebSocket client with automatic reconnection (exponential back-off). Events are pushed
// by the server; the UI never polls per frame.

import type { WsMessage } from "./types";

export type WsStatus = "connecting" | "open" | "closed";

export class LiveSocket {
  private ws: WebSocket | null = null;
  private retry = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private stopped = false;
  private path: string;
  private onMessage: (m: WsMessage) => void;
  private onStatus: (s: WsStatus) => void;

  constructor(path: string, onMessage: (m: WsMessage) => void, onStatus: (s: WsStatus) => void) {
    this.path = path;
    this.onMessage = onMessage;
    this.onStatus = onStatus;
  }

  start(): void {
    this.stopped = false;
    this.connect();
  }

  stop(): void {
    this.stopped = true;
    if (this.timer) clearTimeout(this.timer);
    this.ws?.close();
    this.ws = null;
  }

  private connect(): void {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    this.onStatus("connecting");
    const ws = new WebSocket(`${proto}://${location.host}${this.path}`);
    this.ws = ws;
    ws.onopen = () => {
      this.retry = 0;
      this.onStatus("open");
    };
    ws.onmessage = (ev) => {
      try {
        this.onMessage(JSON.parse(ev.data));
      } catch {
        /* ignore malformed */
      }
    };
    ws.onclose = () => {
      this.onStatus("closed");
      if (this.stopped) return;
      const delay = Math.min(10_000, 500 * 2 ** this.retry++);
      this.timer = setTimeout(() => this.connect(), delay);
    };
    ws.onerror = () => ws.close();
  }
}
