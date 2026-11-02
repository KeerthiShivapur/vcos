const fs = require('fs');
const code = fs.readFileSync('components/collaboration/CommentThread.tsx', 'utf8');
let inTemplate = false;
let inString = false;
let stringChar = '';
let templateStart = -1;

for (let i = 0; i < code.length; i++) {
    const c = code[i];
    const next = code[i+1];
    
    if (!inTemplate && !inString) {
        if (c === '`') {
            inTemplate = true;
            templateStart = i;
        } else if (c === '"' || c === "'") {
            inString = true;
            stringChar = c;
        }
    } else if (inTemplate) {
        if (c === '`') {
            inTemplate = false;
        } else if (c === '$' && code[i+1] === '{') {
            // template expression
        }
    } else if (inString) {
        if (c === stringChar && code[i-1] !== '\\') {
            inString = false;
        }
    }
    
    if (inTemplate && i === code.length - 1) {
        console.log('Unclosed template at end of file, started at:', templateStart);
        console.log('Context:', code.substring(Math.max(0, templateStart-50), templateStart+50));
    }
}

console.log('Done checking templates');