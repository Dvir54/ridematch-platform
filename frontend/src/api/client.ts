import { env } from '../env'
import { ApiError } from './errors'
import type { ApiErrorBody } from './types'

type TokenProvider = () => Promise<string | null>

let tokenProvider: TokenProvider = async () => null

/**
 * Clerk owns the session token and refreshes it on its own, so the client asks
 * for a fresh one before every call (CONTRACT §2). `<ApiTokenBridge/>` installs
 * the provider once Clerk has loaded.
 */
export function setTokenProvider(provider: TokenProvider): void {
  tokenProvider = provider
}

export type QueryValue = string | number | boolean | null | undefined
export type Query = Record<string, QueryValue>

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  query?: Query
  body?: unknown
  signal?: AbortSignal
}

function buildUrl(path: string, query?: Query): string {
  const url = new URL(`${env.apiBaseUrl.replace(/\/$/, '')}${path}`)
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, String(value))
    }
  }
  return url.toString()
}

const UNEXPECTED: ApiErrorBody = {
  code: 'UNEXPECTED_RESPONSE',
  message: 'The server returned something this app could not read.',
}

async function readErrorBody(response: Response): Promise<ApiErrorBody> {
  try {
    const body: unknown = await response.json()
    if (
      body !== null &&
      typeof body === 'object' &&
      typeof (body as ApiErrorBody).code === 'string' &&
      typeof (body as ApiErrorBody).message === 'string'
    ) {
      return body as ApiErrorBody
    }
  } catch {
    /* fall through to the generic envelope */
  }
  return UNEXPECTED
}

/** Issues one authenticated call and returns the parsed body, or throws `ApiError`. */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', query, body, signal } = options

  const headers = new Headers({ Accept: 'application/json' })
  const token = await tokenProvider()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (body !== undefined) headers.set('Content-Type', 'application/json')

  let response: Response
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers,
      signal,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
    throw new ApiError(0, {
      code: 'NETWORK_ERROR',
      message: 'The request never reached RideMatch.',
    })
  }

  if (!response.ok) {
    throw new ApiError(response.status, await readErrorBody(response))
  }

  if (response.status === 204) return undefined as T

  try {
    return (await response.json()) as T
  } catch {
    throw new ApiError(response.status, UNEXPECTED)
  }
}

export interface ListResult<T> {
  data: T[]
  /** From `X-Total-Count` — admin lists only (CONTRACT §2). */
  total: number
}

/** Like `request`, but reads `X-Total-Count` off the response instead of discarding it. */
export async function requestList<T>(path: string, options: RequestOptions = {}): Promise<ListResult<T>> {
  const { method = 'GET', query, signal } = options

  const headers = new Headers({ Accept: 'application/json' })
  const token = await tokenProvider()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  let response: Response
  try {
    response = await fetch(buildUrl(path, query), { method, headers, signal })
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
    throw new ApiError(0, { code: 'NETWORK_ERROR', message: 'The request never reached RideMatch.' })
  }

  if (!response.ok) throw new ApiError(response.status, await readErrorBody(response))

  const total = Number(response.headers.get('X-Total-Count') ?? 0) || 0
  try {
    return { data: (await response.json()) as T[], total }
  } catch {
    throw new ApiError(response.status, UNEXPECTED)
  }
}

export const api = {
  get: <T>(path: string, query?: Query, signal?: AbortSignal) =>
    request<T>(path, { method: 'GET', query, signal }),
  getList: <T>(path: string, query?: Query, signal?: AbortSignal) =>
    requestList<T>(path, { method: 'GET', query, signal }),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body }),
  patch: <T>(path: string, body: unknown) => request<T>(path, { method: 'PATCH', body }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}
