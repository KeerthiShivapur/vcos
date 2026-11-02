const fs = require('fs');
let code = fs.readFileSync('app/(app)/embedded-analytics/page.tsx', 'utf8');
const lines = code.split('\n');
for(let i=258; i<265; i++) {
    console.log((i+1).toString().padStart(4), JSON.stringify(lines[i]));
}