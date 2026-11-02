const fs = require('fs');
const code = fs.readFileSync('components/collaboration/CommentThread.tsx', 'utf8');
const lines = code.split('\n');
for(let i=500; i<505; i++) {
    console.log((i+1) + ': [' + lines[i] + ']');
}