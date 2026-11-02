const fs = require('fs');
const code = fs.readFileSync('components/collaboration/CommentThread.tsx', 'utf8');
const regex = /`[^`]*\$\{[^}]*\}[^`]*$/gm;
const matches = code.matchAll(regex);
for (const m of matches) {
    console.log('Unclosed template at position:', m.index);
    console.log('Context:', code.substring(Math.max(0, m.index-50), m.index+50));
}