const fs = require('fs');
let code = fs.readFileSync('app/(app)/meetings/[meetingId]/page.tsx', 'utf8');

// Fix the early return pattern - assign JSX to variable (with LF)
const oldCode = `  );\n\n  return (`;

const newCode = `  );\n\n  const content = (`;

if (code.includes(oldCode)) {
  code = code.replace(oldCode, newCode);
  
  // Also fix the closing - change `); }` to `); return content; }`
  const oldClose = `);\n}\n`;
  const newClose = `);\n  return content;\n}\n`;
  
  if (code.includes(oldClose)) {
    code = code.replace(oldClose, newClose);
    fs.writeFileSync('app/(app)/meetings/[meetingId]/page.tsx', code);
    console.log('Fixed meeting page');
  } else {
    console.log('Close pattern not found');
  }
} else {
  console.log('Pattern not found');
}