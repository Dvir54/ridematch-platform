import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Notification } from '../api/types'
import type { MinimalSocket } from './socketClient'
import { NotificationSocket } from './socketClient'

class FakeSocket implements MinimalSocket {
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: ((event: { code: number }) => void) | null = null
  onerror: (() => void) | null = null
  sent: string[] = []
  closed = false
  readonly url: string

  constructor(url: string) {
    this.url = url
  }

  send(data: string): void {
    this.sent.push(data)
  }

  close(): void {
    this.closed = true
  }
}

let sockets: FakeSocket[]

function createSocket(url: string): MinimalSocket {
  const socket = new FakeSocket(url)
  sockets.push(socket)
  return socket
}

const sampleNotification: Notification = {
  id: 1,
  type: 'welcome',
  title: 'Welcome',
  message: 'Glad to have you.',
  related_entity_type: null,
  related_entity_id: null,
  is_read: false,
  created_at: '2026-01-01T00:00:00Z',
}

beforeEach(() => {
  vi.useFakeTimers()
  sockets = []
})

afterEach(() => {
  vi.useRealTimers()
})

describe('NotificationSocket', () => {
  it('connects with a fresh token in the query string', async () => {
    const getToken = vi.fn().mockResolvedValue('tok-1')
    const socket = new NotificationSocket({
      url: 'ws://x/ws',
      getToken,
      onNotification: vi.fn(),
      createSocket,
    })

    socket.connect()
    await vi.advanceTimersByTimeAsync(0)

    expect(sockets).toHaveLength(1)
    expect(sockets[0].url).toBe('ws://x/ws?token=tok-1')
  })

  it('pings every 25s once open, and stops once disconnected', async () => {
    const socket = new NotificationSocket({
      url: 'ws://x',
      getToken: vi.fn().mockResolvedValue('tok'),
      onNotification: vi.fn(),
      createSocket,
    })
    socket.connect()
    await vi.advanceTimersByTimeAsync(0)
    sockets[0].onopen?.()

    await vi.advanceTimersByTimeAsync(25_000)
    expect(sockets[0].sent).toEqual([JSON.stringify({ event: 'ping' })])
    await vi.advanceTimersByTimeAsync(25_000)
    expect(sockets[0].sent).toHaveLength(2)

    socket.disconnect()
    await vi.advanceTimersByTimeAsync(50_000)
    expect(sockets[0].sent).toHaveLength(2)
  })

  it('delivers a pushed notification to the handler', async () => {
    const onNotification = vi.fn()
    const socket = new NotificationSocket({
      url: 'ws://x',
      getToken: vi.fn().mockResolvedValue('tok'),
      onNotification,
      createSocket,
    })
    socket.connect()
    await vi.advanceTimersByTimeAsync(0)
    sockets[0].onopen?.()

    sockets[0].onmessage?.({
      data: JSON.stringify({ event: 'notification', data: sampleNotification }),
    })

    expect(onNotification).toHaveBeenCalledWith(sampleNotification)
  })

  it('ignores a non-notification server message', async () => {
    const onNotification = vi.fn()
    const socket = new NotificationSocket({
      url: 'ws://x',
      getToken: vi.fn().mockResolvedValue('tok'),
      onNotification,
      createSocket,
    })
    socket.connect()
    await vi.advanceTimersByTimeAsync(0)
    sockets[0].onopen?.()

    sockets[0].onmessage?.({ data: JSON.stringify({ event: 'pong' }) })

    expect(onNotification).not.toHaveBeenCalled()
  })

  it('fetches a fresh token and reconnects with growing backoff after 4401', async () => {
    const getToken = vi.fn().mockResolvedValue('tok')
    const socket = new NotificationSocket({
      url: 'ws://x',
      getToken,
      onNotification: vi.fn(),
      createSocket,
    })
    socket.connect()
    await vi.advanceTimersByTimeAsync(0)
    expect(sockets).toHaveLength(1)

    sockets[0].onclose?.({ code: 4401 })
    expect(sockets).toHaveLength(1) // not yet — waiting out the backoff
    await vi.advanceTimersByTimeAsync(999)
    expect(sockets).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(sockets).toHaveLength(2)
    expect(getToken).toHaveBeenCalledTimes(2)

    // Second failure in a row waits twice as long (2s, not 1s again).
    sockets[1].onclose?.({ code: 4401 })
    await vi.advanceTimersByTimeAsync(1_999)
    expect(sockets).toHaveLength(2)
    await vi.advanceTimersByTimeAsync(1)
    expect(sockets).toHaveLength(3)
  })

  it('resets the backoff after a successful open', async () => {
    const socket = new NotificationSocket({
      url: 'ws://x',
      getToken: vi.fn().mockResolvedValue('tok'),
      onNotification: vi.fn(),
      createSocket,
    })
    socket.connect()
    await vi.advanceTimersByTimeAsync(0)
    sockets[0].onclose?.({ code: 1006 })
    await vi.advanceTimersByTimeAsync(1_000)
    expect(sockets).toHaveLength(2)

    sockets[1].onopen?.() // this attempt succeeds
    sockets[1].onclose?.({ code: 1006 })
    await vi.advanceTimersByTimeAsync(999)
    expect(sockets).toHaveLength(2)
    await vi.advanceTimersByTimeAsync(1)
    expect(sockets).toHaveLength(3) // back to the 1s starting delay, not 2s
  })

  it('stops reconnecting after a 4403 close (deactivated account)', async () => {
    const socket = new NotificationSocket({
      url: 'ws://x',
      getToken: vi.fn().mockResolvedValue('tok'),
      onNotification: vi.fn(),
      createSocket,
    })
    socket.connect()
    await vi.advanceTimersByTimeAsync(0)

    sockets[0].onclose?.({ code: 4403 })
    await vi.advanceTimersByTimeAsync(60_000)

    expect(sockets).toHaveLength(1)
  })

  it('disconnect closes the socket and cancels any pending reconnect', async () => {
    const socket = new NotificationSocket({
      url: 'ws://x',
      getToken: vi.fn().mockResolvedValue('tok'),
      onNotification: vi.fn(),
      createSocket,
    })
    socket.connect()
    await vi.advanceTimersByTimeAsync(0)
    sockets[0].onclose?.({ code: 1006 })

    socket.disconnect()
    await vi.advanceTimersByTimeAsync(60_000)

    expect(sockets).toHaveLength(1)
    expect(sockets[0].closed).toBe(true)
  })
})
