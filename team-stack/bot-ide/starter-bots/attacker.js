const axios = require('axios');

const ORCH = process.env.ORCH || process.env.ORCHESTRATOR_URL || 'http://orchestrator:9000';
const MY_TARGET = process.env.MY_TARGET || 'http://localhost:9100';
const SECRET = process.env.HACKATHON_SECRET || 'HACKATHON_SECRET_2025';

async function activeService() {
  try {
    const r = await axios.get(`${ORCH}/current`, { timeout: 3000 });
    return r.data.active_service || 'web';
  } catch (_) {
    return 'web';
  }
}

async function tick() {
  const vulns = ['sql_injection', 'xss', 'csrf', 'rce', 'auth_bypass'];
  const service = await activeService();
  const vuln = vulns[Math.floor(Math.random() * vulns.length)];
  try {
    const r = await axios.post(`${MY_TARGET}/${service}/attack`, {
      vulnerability_type: vuln,
      service,
      secret: SECRET,
    }, { timeout: 5000 });
    console.log(`attack ${service}/${vuln} -> ${r.status}`);
  } catch (e) {
    console.log(`attack error: ${e.message}`);
  }
}

console.log('[attacker.js] started');
setInterval(tick, 3000);
