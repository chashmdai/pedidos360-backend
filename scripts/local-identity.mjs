// Development fixture only. It is not Microsoft Entra and must never be deployed.
import { createServer } from 'node:http'
import { generateKeyPairSync, createPrivateKey, createPublicKey, sign } from 'node:crypto'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'

const directory = join(homedir(), '.config/pedidos360/local')
mkdirSync(directory, { recursive: true, mode: 0o700 })
const keyPath = join(directory, 'local-identity-private.pem')
if (!existsSync(keyPath)) {
  const pair = generateKeyPairSync('rsa', { modulusLength: 2048 })
  writeFileSync(keyPath, pair.privateKey.export({ type: 'pkcs8', format: 'pem' }), { mode: 0o600, flag: 'wx' })
}
const key = createPrivateKey(readFileSync(keyPath))
const jwk = { ...createPublicKey(key).export({ format: 'jwk' }), kid: 'pedidos360-local', alg: 'RS256', use: 'sig' }
const issuer = 'http://127.0.0.1:8190'
const encode = value => Buffer.from(JSON.stringify(value)).toString('base64url')
function token(options = {}) {
  const now = Math.floor(Date.now() / 1000)
  const claims = {
    iss: options.issuer ?? issuer, aud: options.audience ?? 'pedidos360-local-api',
    sub: options.subject ?? 'demo-user', oid: options.subject ?? 'demo-user', tid: 'local-development',
    azp: 'pedidos360-local-spa', ver: '2.0', name: 'Usuario de demostración', iat: now, nbf: now - 5, exp: now + (options.ttl ?? 600),
    scp: options.scopes ?? 'Catalog.Read Orders.Read Orders.Create', roles: options.roles ?? ['User'],
  }
  const input = encode({ alg: 'RS256', typ: 'JWT', kid: jwk.kid }) + '.' + encode(claims)
  return input + '.' + sign('RSA-SHA256', Buffer.from(input), key).toString('base64url')
}
if (process.argv[2] === 'token') {
  // Consumers capture stdout in memory; never paste this output into evidence or logs.
  process.stdout.write(token(process.argv[3] ? JSON.parse(process.argv[3]) : {}))
} else if (process.argv[2] === 'serve') {
  const allowed = new Set(['http://localhost:5173', 'http://127.0.0.1:5173'])
  createServer((request, response) => {
    const origin = request.headers.origin
    if (!['127.0.0.1:8190', 'localhost:8190'].includes(request.headers.host) || (origin && !allowed.has(origin))) {
      response.writeHead(403).end(); return
    }
    if (origin) { response.setHeader('Access-Control-Allow-Origin', origin); response.setHeader('Vary', 'Origin') }
    response.setHeader('Cache-Control', 'no-store')
    response.setHeader('Content-Type', 'application/json')
    if (request.method === 'OPTIONS') {
      response.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
      response.setHeader('Access-Control-Allow-Headers', 'Content-Type')
      response.writeHead(204).end(); return
    }
    if (request.method === 'GET' && request.url === '/jwks') response.end(JSON.stringify({ keys: [jwk] }))
    else if (request.method === 'GET' && request.url === '/health') response.end('{"status":"UP","mode":"LOCAL_FIXTURE"}')
    else if (request.method === 'POST' && request.url === '/token') response.end(JSON.stringify({ accessToken: token(), mode: 'LOCAL_FIXTURE' }))
    else response.writeHead(404).end('{}')
  }).listen(8190, '127.0.0.1', () => console.log('Pedidos360 local JWT fixture listening on 127.0.0.1:8190'))
} else {
  console.error('Usage: node scripts/local-identity.mjs serve | token [options-json]')
  process.exitCode = 1
}
