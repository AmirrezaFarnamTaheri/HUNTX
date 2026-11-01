// HUNTX Real-Time WebSocket Telemetry Stream Client
// Auto-reconnecting resilient stream with exponential backoff.

export class TelemetryStreamClient {
  constructor(endpoint = null) {
    this.endpoint = endpoint || (window.location.protocol === "https:" ? "wss://" : "ws://") + window.location.host + "/ws/telemetry";
    this.ws = null;
    this.reconnectAttempts = 0;
    this.listeners = new Map();
  }

  connect() {
    try {
      this.ws = new WebSocket(this.endpoint);

      this.ws.onopen = () => {
        this.reconnectAttempts = 0;
        this.emit("status", { state: "CONNECTED" });
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.emit(data.event_type || "message", data.payload);
        } catch (e) {
          console.warn("[HUNTX-STREAM] Failed to parse message:", e);
        }
      };

      this.ws.onclose = () => {
        this.emit("status", { state: "DISCONNECTED" });
        this.scheduleReconnect();
      };

      this.ws.onerror = (err) => {
        this.emit("error", err);
      };
    } catch (e) {
      this.scheduleReconnect();
    }
  }

  scheduleReconnect() {
    this.reconnectAttempts++;
    const delay = Math.min(10000, 1000 * Math.pow(1.5, this.reconnectAttempts));
    setTimeout(() => this.connect(), delay);
  }

  on(event, callback) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, []);
    }
    this.listeners.get(event).push(callback);
  }

  emit(event, data) {
    const list = this.listeners.get(event) || [];
    list.forEach(cb => cb(data));
  }
}
