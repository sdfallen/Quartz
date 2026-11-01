import { Worker } from '@notionhq/workers';
import { j } from '@notionhq/workers/schema-builder';
import { sign, verify, requestFromGrant } from './envelope.js';
import type {Json} from './envelope.js';

const worker = new Worker();
export default worker;

function settings() {
  const queue = process.env.QUARTZ_QUEUE_ID || '';
  const key = process.env.QUARTZ_BRIDGE_KEY || '';
  if (!/^[a-f0-9-]{36}$/.test(queue) || !/^[a-f0-9]{64}$/.test(key)) throw new Error('Bridge is not configured');
  return {queue, key};
}
function textProperty(page: any, name: string): string {
  return (page.properties?.[name]?.rich_text || []).map((t: any) => t.plain_text ?? t.text?.content ?? '').join('');
}
function ownedPage(page: any, queue: string) {
  if (page.archived || page.in_trash || page.parent?.data_source_id !== queue) throw new Error('Page is outside bridge queue');
}
function rich(text: string) {
  const pieces = [];
  for (let i = 0; i < text.length; i += 1800) pieces.push({type: 'text' as const, text: {content: text.slice(i, i + 1800)}});
  return {rich_text: pieces};
}

worker.tool('quartzReadTestFile', {
  title: 'Quartz test dosyasını oku',
  description: 'Yalnız açık Quartz test görevinin imzalı izniyle belirtilen test dosyasının okunmasını kuyruğa alır. Yerel işlem henüz tamamlanmaz; queued sonucunu başarı sayma. Kendi kendine izin veya yeni dosya yolu üretme. Sonuç hazır bildirildiğinde quartzReadResult kullan.',
  schema: j.object({grant_page_id: j.string().describe('Quartz tarafından verilen izin sayfası ID.'),
    request_id: j.string().describe('Quartz tarafından verilen tek işlem ID.'),
    relative_path: j.string().describe('İzinli test dosyası adı; örnek fixture.txt.')}),
  // No readOnlyHint: enqueue writes queue state and must not bypass Notion
  // confirmation or local owner approval.
  execute: async (input, {notion}): Promise<Record<string, Json>> => {
    try {
      const {queue, key} = settings();
      const grantPage: any = await notion.pages.retrieve({page_id: input.grant_page_id});
      ownedPage(grantPage, queue);
      const grant = verify(textProperty(grantPage, 'Signed Result'), 'grant', key);
      const request = requestFromGrant(grant, input.request_id, input.relative_path, Date.now()/1000);
      const existing = await notion.dataSources.query({data_source_id: queue,
        filter: {property: 'Name', title: {equals: input.request_id}}, page_size: 2});
      if (existing.results.length) {
        if (existing.results.length !== 1) throw new Error('Duplicate queue records');
        const row: any = existing.results[0];
        ownedPage(row, queue);
        const old = verify(textProperty(row, 'Signed Request'), 'request', key);
        if (JSON.stringify(old) !== JSON.stringify(request)) throw new Error('Request binding mismatch');
        return {status: 'queued', request_page_id: row.id, request_id: input.request_id, verification: 'none'};
      }
      const envelope = JSON.stringify(sign('request', request, key));
      const row = await notion.pages.create({parent: {type:'data_source_id', data_source_id: queue}, properties: {
        Name: {title: [{text: {content: input.request_id}}]},
        'Task ID': rich(String(request.task_id)), 'Session ID': rich(String(request.session_id)),
        'Project ID': rich(String(request.project_id)), State: {select: {name: 'requested'}},
        'Expires At': {date: {start: new Date(Number(request.expires_at)*1000).toISOString()}},
        'Signed Request': rich(envelope)
      }});
      return {status: 'queued', request_page_id: row.id, request_id: input.request_id, verification: 'none'};
    } catch {
      return {status: 'blocked', message: 'İzin, kuyruk erişimi veya istek doğrulanamadı. Yerel işlem yapılmış sayılmaz.', verification: 'none'};
    }
  }
});

worker.tool('quartzReadResult', {
  title: 'Quartz test sonucunu oku',
  description: 'Quartz yerel test okumasının hazır olduğunu bildirdiğinde imzalı sonucu getirir. Yeni yerel işlem başlatmaz; pending varsa durup hazır bildirimini bekle.',
  schema: j.object({request_page_id: j.string().describe('Quartz test isteğinin sayfa ID.')}),
  hints: {readOnlyHint: true},
  execute: async ({request_page_id}, {notion}): Promise<Record<string, Json>> => {
    try {
      const {queue, key} = settings();
      const page: any = await notion.pages.retrieve({page_id: request_page_id});
      ownedPage(page, queue);
      const raw = textProperty(page, 'Signed Result');
      if (!raw) return {status: 'pending', verification: 'none'};
      const request = verify(textProperty(page, 'Signed Request'), 'request', key);
      const result = verify(raw, 'result', key);
      if (['request_id','session_id','task_id','project_id'].some(k => result[k] !== request[k])) throw new Error('Result binding mismatch');
      return result;
    } catch {
      return {status: 'blocked', message: 'Sonuç imzası veya kuyruk erişimi doğrulanamadı.', verification: 'none'};
    }
  }
});
