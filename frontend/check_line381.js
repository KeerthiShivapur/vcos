const fs = require('fs');
const code = fs.readFileSync('components/collaboration/CommentThread.tsx', 'utf8');
const lines = code.split('\n');
console.log(JSON.stringify(lines[380]));