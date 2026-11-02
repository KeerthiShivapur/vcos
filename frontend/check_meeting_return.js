const fs = require('fs');
let code = fs.readFileSync('app/(app)/meetings/[meetingId]/page.tsx', 'utf8');
const lines = code.split('\n');
for(let i=345; i<355; i++) {
    console.log((i+1).toString().padStart(4), JSON.stringify(lines[i]));
}