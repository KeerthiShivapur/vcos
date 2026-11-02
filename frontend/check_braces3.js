const fs = require('fs');
const code = fs.readFileSync('components/collaboration/CommentThread.tsx', 'utf8');

let braces = 0;
for (let i = 0; i < code.length; i++) {
    const c = code[i];
    if (c === '{') {
        braces++;
        if (braces > 1) {
            console.log(`{ at ${i}: braces=${braces}, context: ${code.substring(Math.max(0,i-30), i+30)}`);
        }
    } else if (c === '}') {
        braces--;
        if (braces < 0) {
            console.log(`Negative at ${i}`);
            break;
        }
    }
}

console.log('Final braces:', braces);