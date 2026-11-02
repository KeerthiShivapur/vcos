const fs = require('fs');
const code = fs.readFileSync('components/collaboration/CommentThread.tsx', 'utf8');
const lines = code.split('\n');
for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    let backtickCount = 0;
    for (let j = 0; j < line.length; j++) {
        if (line[j] === '`') {
            console.log(`Backtick at line ${i+1}, char ${j}: ${line.substring(Math.max(0, j-20), j+20)}`);
        }
    }
}