const fs = require('fs');
const code = fs.readFileSync('components/collaboration/CommentThread.tsx', 'utf8');

let braces = 0;
let inString = false;
let stringChar = '';
let inTemplate = false;
let inJSX = false;
let jsxDepth = 0;

for (let i = 0; i < code.length; i++) {
    const c = code[i];
    const next = code[i+1];
    
    // Handle string literals
    if ((c === '"' || c === "'" || c === '`') && code[i-1] !== '\\') {
        if (!inString) {
            inString = true;
            stringChar = c;
            if (c === '`') inTemplate = true;
        } else if (c === stringChar && !inTemplate) {
            inString = false;
            stringChar = '';
        } else if (c === '`' && inTemplate) {
            inTemplate = false;
        }
        continue;
    }
    
    if (inString) continue;
    
    // Handle JSX
    if (c === '<' && next !== '/' && code[i-1] !== '{') {
        inJSX = true;
        jsxDepth++;
        continue;
    }
    if (c === '/' && next === '>' && inJSX) {
        jsxDepth--;
        if (jsxDepth === 0) inJSX = false;
        continue;
    }
    if (c === '<' && next === '/' && inJSX) {
        continue;
    }
    
    if (inJSX) continue;
    
    // Count braces outside strings and JSX
    if (c === '{') {
        braces++;
        console.log(`{ at ${i}: braces=${braces}`);
    } else if (c === '}') {
        braces--;
        console.log(`} at ${i}: braces=${braces}`);
        if (braces < 0) {
            console.log('Negative braces at', i);
            break;
        }
    }
}

console.log('Final braces:', braces);