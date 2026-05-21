const axios = require('axios');

const MY_TARGET = process.env.MY_TARGET || 'http://localhost:9100';
const SECRET = process.env.HACKATHON_SECRET || 'HACKATHON_SECRET_2025';
const serviceVulns = {
  web: ['sqli', 'xss', 'auth_bypass'],
  api: ['insecure_ep', 'cmd_inject', 'idor'],
  file: ['path_traversal', 'exec_upload'],
  db: ['sqli', 'priv_esc'],
};

async function tick() {
  try {
    for (const [service, vulns] of Object.entries(serviceVulns)) {
      const health = await axios.get(`${MY_TARGET}/${service}/health`, { timeout: 5000 });
      console.log(`health ${service} -> ${health.status}`);
      for (const vuln of vulns) {
        const r = await axios.post(`${MY_TARGET}/${service}/flags/deactivate`, {
          secret: SECRET,
          vuln,
        }, { timeout: 5000 });
        console.log(`deactivate ${service}/${vuln} -> ${r.status}`);
      }
      if (health.data && typeof health.data.hp === 'number' && typeof health.data.max_hp === 'number' && health.data.hp < health.data.max_hp) {
        const heal = await axios.post(`${MY_TARGET}/${service}/heal`, { secret: SECRET, amount: 5 }, { timeout: 5000 });
        console.log(`heal ${service} -> ${heal.status}`);
      }
    }
  } catch (e) {
    console.log(`defend error: ${e.message}`);
  }
}

console.log('[defender.js] started');
setInterval(tick, 4000);
