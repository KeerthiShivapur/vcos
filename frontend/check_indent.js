const fs = require('fs');
const code = fs.readFileSync('hooks/useComments.ts', 'utf8');
const lines = code.split('\n');
for(let i=207; i<228; i++) {
    console.log((i+1).toString().padStart(4), JSON.stringify(lines[i]));
}