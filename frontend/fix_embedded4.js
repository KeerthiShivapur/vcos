const fs = require('fs');
let code = fs.readFileSync('app/(app)/embedded-analytics/page.tsx', 'utf8');

// Fix the early return pattern - assign JSX to variable (with CRLF)
const oldCode = `  };\r\n\r\n  return (`;

const newCode = `  };\r\n\r\n  const content = (`;

if (code.includes(oldCode)) {
  code = code.replace(oldCode, newCode);
  
  // Also fix the closing - change `); }` to `); return content; }`
  const oldClose = `);\r\n}\r`;
  const newClose = `);\r\n  return content;\r\n}\r`;
  
  if (code.includes(oldClose)) {
    code = code.replace(oldClose, newClose);
    fs.writeFileSync('app/(app)/embedded-analytics/page.tsx', code);
    console.log('Fixed embedded-analytics page 2');
  } else {
    console.log('Close pattern not found');
  }
} else {
  console.log('Pattern not found');
}