const fs = require('node:fs');
const path = require('node:path');

function readDotEnvValue(name) {
  const envPath = path.resolve(__dirname, '..', '.env');
  if (!fs.existsSync(envPath)) {
    return '';
  }
  const contents = fs.readFileSync(envPath, 'utf8');
  const line = contents
    .split(/\r?\n/)
    .find((item) => item.trimStart().startsWith(`${name}=`));
  if (!line) {
    return '';
  }
  return line
    .slice(line.indexOf('=') + 1)
    .trim()
    .replace(/^['"]|['"]$/g, '');
}

const apiToken = process.env.APPOINTMENT_BOT_API_TOKEN || readDotEnvValue('APPOINTMENT_BOT_API_TOKEN');
const authHeaders = apiToken ? { Authorization: `Bearer ${apiToken}` } : {};

module.exports = {
  '/api': {
    target: 'http://127.0.0.1:8766',
    secure: false,
    changeOrigin: false,
    logLevel: 'info',
    headers: authHeaders,
  },
  '/health': {
    target: 'http://127.0.0.1:8766',
    secure: false,
    changeOrigin: false,
    logLevel: 'info',
  },
};
