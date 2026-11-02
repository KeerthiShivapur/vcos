const fs = require('fs');
const code = fs.readFileSync('components/collaboration/CommentThread.tsx', 'utf8');
let braces = 0;
let parens = 0;
let brackets = 0;
for (let i = 0; i < code.length; i++) {
    const c = code[i];
    if (c === '{') braces++;
    else if (c === '}') braces--;
    else if (c === '(') parens++;
    else if (c === ')') parens--;
    else if (c === '[') brackets++;
    else if (c === ']') brackets--;
    if (braces < 0 || parens < 0 || brackets < 0) {
        console.log('Negative at', i, 'braces:', braces, 'parens:', parens, 'brackets:', brackets);
        console.log('Context:', code.substring(Math.max(0, i-50), i+50));
        break;
    }
}
console.log('Final:', 'braces:', braces, 'parens:', parens, 'brackets:', brackets);