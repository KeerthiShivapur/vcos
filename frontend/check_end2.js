const fs = require('fs');
const code = fs.readFileSync('components/collaboration/CommentThread.tsx', 'utf8');
const lines = code.split('\n');
for(let i=540; i<550; i++) {
    console.log((i+1).toString().padStart(4), '|' + lines[i] + '|');
}