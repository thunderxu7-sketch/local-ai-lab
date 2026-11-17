// Syntax checks and execution of static, authored fixtures only. Never model output.
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const { createRequire } = require('node:module');
const appRequire = createRequire(path.resolve(__dirname, '../../qwen-chat-lab/package.json'));
const ts = appRequire('typescript');
const postcss = appRequire('postcss');
const scenarios = JSON.parse(fs.readFileSync(0, 'utf8'));
const syntax = [], probes = [], tokens = {};

for (const scenario of scenarios) {
  for (const variant of ['buggy', 'fixed']) {
    const code = scenario[variant];
    const id = scenario.id + (variant === 'buggy' ? '-bug' : '-ok');
    const extension = scenario.filename.split('.').pop();
    if (['js', 'jsx', 'ts', 'tsx'].includes(extension)) {
      const kind = {js: ts.ScriptKind.JS, jsx: ts.ScriptKind.JSX, ts: ts.ScriptKind.TS, tsx: ts.ScriptKind.TSX}[extension];
      const ast = ts.createSourceFile(scenario.filename, code, ts.ScriptTarget.Latest, true, kind);
      syntax.push({id, method: 'typescript-parser-only', errors: ast.parseDiagnostics.map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n'))});
      const sequence = [];
      function visit(node) {
        if (node.getChildCount(ast) === 0) {
          let token = node.getText(ast);
          if (ts.isIdentifier(node)) {
            const p = node.parent;
            const preserve = (ts.isPropertyAccessExpression(p) && p.name === node)
              || ((ts.isPropertyAssignment(p) || ts.isJsxAttribute(p)) && p.name === node)
              || ((ts.isJsxOpeningElement(p) || ts.isJsxClosingElement(p) || ts.isJsxSelfClosingElement(p)) && p.tagName === node)
              || ts.isImportSpecifier(p);
            if (!preserve) token = '$IDENTIFIER';
          } else if (ts.isStringLiteral(node) || ts.isNumericLiteral(node) || ts.isJsxText(node)) {
            token = '$LITERAL';
          }
          if (token.trim()) sequence.push(token);
        } else {
          for (const child of node.getChildren(ast)) visit(child);
        }
      }
      visit(ast);
      tokens[id] = sequence;
    } else if (extension === 'css') {
      const errors = [];
      try { postcss.parse(code, {from: scenario.filename}); } catch (e) { errors.push(e.message); }
      syntax.push({id, method: 'postcss-parser-only', errors});
    }
    if (scenario.probe) {
      let observed;
      try {
        const value = vm.runInNewContext(code + '\n' + scenario.probe, {URL}, {timeout: 1000});
        observed = value === undefined ? {type: 'undefined'} :
          typeof value === 'number' && !Number.isFinite(value) ? {type:'nonfinite', value:String(value)} : {type:'value', value};
      } catch (e) { observed = {type:'error', name:e.name, message:e.message}; }
      const matches = observed.type === 'value' && JSON.stringify(observed.value) === JSON.stringify(scenario.expected);
      probes.push({id, expression:scenario.probe, expected:scenario.expected, observed,
        passed: variant === 'fixed' ? matches : !matches});
    }
  }
}
process.stdout.write(JSON.stringify({syntax, probes, tokens}));
