import { createHmac, timingSafeEqual } from 'node:crypto';

export type Envelope = {v: number; kind: string; body: string; mac: string};
export type Json = null | string | number | boolean | Json[] | {[key: string]: Json};
export function sign(kind: string, payload: unknown, key: string): Envelope {
  if (!/^[a-f0-9]{64}$/.test(key)) throw new Error('Bridge signing key unavailable');
  const body = JSON.stringify(payload);
  if (Buffer.byteLength(body) > 12000) throw new Error('Bridge payload limit');
  return {v: 1, kind, body,
    mac: createHmac('sha256', Buffer.from(key, 'hex')).update(`quartz-readonly/${kind}/v1\n${body}`).digest('hex')};
}
export function verify(raw: string, kind: string, key: string): Record<string, Json> {
  if (Buffer.byteLength(raw) > 16000 || !/^[a-f0-9]{64}$/.test(key)) throw new Error('Invalid bridge envelope');
  const env = JSON.parse(raw) as Envelope;
  if (env.v !== 1 || env.kind !== kind || typeof env.body !== 'string' || !/^[a-f0-9]{64}$/.test(env.mac))
    throw new Error('Invalid bridge envelope');
  const expected = createHmac('sha256', Buffer.from(key, 'hex')).update(`quartz-readonly/${kind}/v1\n${env.body}`).digest();
  if (!timingSafeEqual(expected, Buffer.from(env.mac, 'hex'))) throw new Error('Invalid bridge signature');
  const data = JSON.parse(env.body);
  if (!data || typeof data !== 'object' || Array.isArray(data)) throw new Error('Invalid bridge payload');
  return data;
}

export function requestFromGrant(grant: Record<string, unknown>, requestId: string, relativePath: string, now: number) {
  const names = ['task_id', 'session_id', 'project_id', 'scope_ref', 'request_id'];
  if (grant.tool_name !== 'read_test_file' || grant.request_id !== requestId || grant.relative_path !== relativePath ||
      typeof grant.expires_at !== 'number' || !Number.isFinite(grant.expires_at) ||
      grant.expires_at <= now || grant.expires_at > now + 1200 ||
      names.some(n => typeof grant[n] !== 'string' || !/^[A-Za-z0-9._:-]{1,128}$/.test(grant[n] as string)) ||
      !/^[A-Za-z0-9_-]{1,64}\.txt$/.test(relativePath)) throw new Error('Grant is invalid or expired');
  return {schema_version: 1, task_id: grant.task_id, session_id: grant.session_id,
    project_id: grant.project_id, scope_ref: grant.scope_ref, request_id: requestId,
    tool_name: 'read_test_file', arguments: {relative_path: relativePath}, expires_at: grant.expires_at};
}
