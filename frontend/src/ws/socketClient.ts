import type { Notification } from '../api/types'
import { backoffDelay } from './backoff'

export type SocketStatus = 'connecting' | 'open' | 'closed'

/** The slice of the browser `WebSocket` API this client actually uses — small
 * enough that tests can fake it without reimplementing the whole interface. */
export interface MinimalSocket {
  onopen: (() => void) | null
  onmessage: ((event: { data: string }) => void) | null
  onclose: ((event: { code: number }) => void) | null
  onerror: (() => void) | null
  send(data: string): void
  close(): void
}

export interface NotificationSocketOptions {
  url: string
  /** A fresh token per connect attempt — Clerk tokens expire in about a minute. */
  getToken: () => Promise<string | null>
  onNotification: (notification: Notification) => void
  onStatusChange?: (status: SocketStatus) => void
  /** Defaults to the browser's `WebSocket`; tests inject a fake. */
  createSocket?: (url: string) => MinimalSocket
  pingIntervalMs?: number
}

const PING_INTERVAL_MS = 25_000
/**
 * CONTRACT §6: a deactivated account closes with 4403 — nothing to reconnect
 * to. Every other close (4401 for no/expired token, or a transport drop) gets
 * a fresh token and reconnects with backoff.
 */
const CODE_DEACTIVATED = 4403

/** Adapts the browser's `WebSocket` (whose handlers take an `Event`) to `MinimalSocket`. */
class BrowserSocket implements MinimalSocket {
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: ((event: { code: number }) => void) | null = null
  onerror: (() => void) | null = null
  private readonly native: WebSocket

  constructor(url: string) {
    this.native = new WebSocket(url)
    this.native.onopen = () => this.onopen?.()
    this.native.onmessage = (event) => this.onmessage?.({ data: event.data as string })
    this.native.onclose = (event) => this.onclose?.({ code: event.code })
    this.native.onerror = () => this.onerror?.()
  }

  send(data: string): void {
    this.native.send(data)
  }

  close(): void {
    this.native.close()
  }
}

function defaultCreateSocket(url: string): MinimalSocket {
  return new BrowserSocket(url)
}

/**
 * Owns one connection to `GET /ws` (CONTRACT §6): fetches a fresh token before
 * every attempt, pings every 25s so the server doesn't drop an idle socket,
 * and reconnects with capped exponential backoff on 4401 or any transport
 * drop. A 4403 (deactivated) stops reconnecting — the account is gone either way.
 */
export class NotificationSocket {
  private readonly opts: NotificationSocketOptions
  private socket: MinimalSocket | null = null
  private pingTimer: ReturnType<typeof setInterval> | null = null
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private attempt = 0
  private stopped = true

  constructor(options: NotificationSocketOptions) {
    this.opts = options
  }

  connect(): void {
    this.stopped = false
    void this.open()
  }

  disconnect(): void {
    this.stopped = true
    this.clearTimers()
    this.socket?.close()
    this.socket = null
  }

  private async open(): Promise<void> {
    if (this.stopped) return
    this.setStatus('connecting')

    const token = await this.opts.getToken()
    if (this.stopped) return
    if (!token) {
      this.scheduleReconnect()
      return
    }

    const createSocket = this.opts.createSocket ?? defaultCreateSocket
    const socket = createSocket(`${this.opts.url}?token=${encodeURIComponent(token)}`)
    this.socket = socket

    socket.onopen = () => {
      this.attempt = 0
      this.setStatus('open')
      this.startPing()
    }
    socket.onmessage = (event) => this.handleMessage(event.data)
    socket.onclose = (event) => this.handleClose(event.code)
    socket.onerror = () => {
      /* onclose always follows; nothing to do here */
    }
  }

  private handleClose(code: number): void {
    this.clearTimers()
    this.setStatus('closed')
    if (this.stopped) return
    if (code === CODE_DEACTIVATED) {
      this.stopped = true
      return
    }
    this.scheduleReconnect()
  }

  private handleMessage(raw: string): void {
    let message: unknown
    try {
      message = JSON.parse(raw)
    } catch {
      return
    }
    if (
      message !== null &&
      typeof message === 'object' &&
      (message as { event?: unknown }).event === 'notification'
    ) {
      this.opts.onNotification((message as { data: Notification }).data)
    }
  }

  private startPing(): void {
    const intervalMs = this.opts.pingIntervalMs ?? PING_INTERVAL_MS
    this.pingTimer = setInterval(() => {
      this.socket?.send(JSON.stringify({ event: 'ping' }))
    }, intervalMs)
  }

  private scheduleReconnect(): void {
    const delay = backoffDelay(this.attempt)
    this.attempt += 1
    this.reconnectTimer = setTimeout(() => void this.open(), delay)
  }

  private clearTimers(): void {
    if (this.pingTimer) clearInterval(this.pingTimer)
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    this.pingTimer = null
    this.reconnectTimer = null
  }

  private setStatus(status: SocketStatus): void {
    this.opts.onStatusChange?.(status)
  }
}
