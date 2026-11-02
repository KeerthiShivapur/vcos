const fs = require('fs');
const code = fs.readFileSync('components/collaboration/CommentThread.tsx', 'utf8');
const regex = /`[^`]*\$\{[^}]*\}[^`]*[^`]/g;
let match;
while ((match = code.match(regex)) !== null) {
    console.log('Unclosed template at position:', match.index);
    console.log('Context:', code.substring(Math.max(0, match.index-50), match.index+50));
    code = code.substring(match.index + match[0].length);
}