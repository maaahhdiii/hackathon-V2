const axios = require('axios');

const MY_TARGET = process.env.MY_TARGET || 'http://localhost:9100';
const vulns = ['sql_injection', 'xss', 'csrf', 'rce', 'auth_bypass'];
const services = ['web', 'api', 'file', 'db'];

async function tick() {
  const vuln = vulns[Math.floor(Math.random() * vulns.length)];
  const service = services[Math.floor(Math.random() * services.length)];
  const action = Math.random() > 0.5 ? 'enable' : 'disable';
  try {
    const r = await axios.post(`${MY_TARGET}/${service}/defend`, {
      service,
      vulnerability_type: vuln,
      action,
    }, { timeout: 5000 });
    console.log(`defend ${service}/${vuln}/${action} -> ${r.status}`);
  } catch (e) {
    console.log(`defend error: ${e.message}`);
  }
}

console.log('[defender.js] started');
setInterval(tick, 4000);
