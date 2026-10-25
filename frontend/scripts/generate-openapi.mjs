import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import { createGenerator } from 'ts-json-schema-generator';
import { stringify } from 'yaml';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const sourcePath = path.join(root, 'contracts/types.ts');
const sourceText = fs.readFileSync(sourcePath, 'utf8');
const source = ts.createSourceFile(sourcePath, sourceText, ts.ScriptTarget.Latest, true);
const compiled = ts.transpileModule(sourceText, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const { API_ROUTES } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const operations = source.statements.find(s => ts.isInterfaceDeclaration(s) && s.name.text === 'ApiOperations');
const generator = createGenerator({ path: sourcePath, type: '*', expose: 'all', additionalProperties: false, skipTypeCheck: false });
const schemas = {};
const operationTypes = {};
for (const member of operations.members) {
  const fields = Object.fromEntries(member.type.members.map(f => [f.name.getText(source), f.type.getText(source)]));
  operationTypes[member.name.getText(source)] = fields;
  for (const name of Object.values(fields).filter(n => n !== 'never')) {
    Object.assign(schemas, generator.createSchema(name).definitions);
  }
}
for (const name of ['ApiError', 'LegacyValidationError', 'ColumnMapping']) {
  Object.assign(schemas, generator.createSchema(name).definitions);
}
const ref = name => ({ $ref: `#/components/schemas/${name}` });
const publicOps = new Set(['health', 'forecastV1', 'advisorV1', 'login', 'capabilities']);
const paths = {};
for (const [operationId, [method, route]] of Object.entries(API_ROUTES)) {
  const { request, response } = operationTypes[operationId];
  const parameters = [...route.matchAll(/\{([^}]+)\}/g)].map(m => ({ name: m[1], in: 'path', required: true, schema: { type: 'string', minLength: 1 } }));
  const code = ['createCompany', 'createEvent'].includes(operationId) ? '201' : '200';
  const legacy = ['forecastV1', 'advisorV1'].includes(operationId);
  const op = {
    operationId,
    tags: [legacy ? 'legacy-v1' : route === '/health' ? 'health' : 'target-v2'],
    description: legacy ? 'Existing API. Synthetic demo only until authentication is enforced.' : route === '/health' ? 'Existing health check.' : 'Target contract. Availability must be confirmed via capabilities.',
    security: publicOps.has(operationId) ? [] : [{ sessionCookie: [] }],
    parameters,
    responses: { [code]: { description: 'Success', content: { 'application/json': { schema: ref(response) } } } },
  };
  if (request !== 'never') {
    if (method === 'get') {
      const schema = schemas[request];
      for (const [name, field] of Object.entries(schema.properties)) {
        parameters.push({ name, in: 'query', required: schema.required?.includes(name) ?? false, schema: field });
      }
    } else {
      op.requestBody = { required: true, content: { [operationId === 'importStatement' ? 'multipart/form-data' : 'application/json']: { schema: ref(request) } } };
    }
  }
  const errorCodes = route === '/health' ? ['503'] : legacy ? ['422', '503'] : ['400', '401', '403', '404', '409', '413', '422', '429', '500', '503'];
  for (const status of errorCodes) op.responses[status] = { description: `HTTP ${status}`, content: { 'application/json': { schema: ref(legacy && status === '422' ? 'LegacyValidationError' : 'ApiError') } } };
  (paths[route] ??= {})[method] = op;
}
schemas.StatementImportForm.properties.file = { type: 'string', format: 'binary' };
schemas.LocalDate = { type: 'string', format: 'date' };
schemas.UtcTimestamp = { type: 'string', format: 'date-time' };
schemas.Probability = { type: 'number', minimum: 0, maximum: 1 };
const document = JSON.parse(JSON.stringify({
  openapi: '3.1.0',
  info: { title: 'Hack RND 2026 Cashflow API', version: '2.0.0', description: 'Generated from types.ts. v1 exists; v2 describes target behavior. Runtime invariants: ARCH_PLAN.md.' },
  servers: [{ url: '/' }], paths,
  components: { securitySchemes: { sessionCookie: { type: 'apiKey', in: 'cookie', name: 'session_id' } }, schemas },
}).replaceAll('#/definitions/', '#/components/schemas/'));
for (const match of JSON.stringify(document).matchAll(/"\$ref":"#\/components\/schemas\/([^"]+)"/g)) {
  if (!document.components.schemas[decodeURIComponent(match[1])]) throw new Error(`Unresolved schema: ${match[1]}`);
}
for (const name of Object.keys(schemas)) {
  if (!/^[a-zA-Z0-9._-]+$/.test(name)) throw new Error(`Invalid OpenAPI component name: ${name}`);
}
if (Object.keys(operationTypes).length !== Object.keys(API_ROUTES).length) throw new Error('Operation catalog mismatch.');
const target = path.join(root, 'contracts/api.yaml');
const output = '# Generated from types.ts; do not edit by hand.\n' + stringify(document, { lineWidth: 120 });
if (process.argv.includes('--check')) {
  if (fs.readFileSync(target, 'utf8').replace(/\r\n/g, '\n') !== output) throw new Error('OpenAPI differs from types.ts. Run npm run contracts.');
} else fs.writeFileSync(target, output);
console.log(`Verified ${Object.keys(API_ROUTES).length} operations and ${Object.keys(schemas).length} schemas.`);
