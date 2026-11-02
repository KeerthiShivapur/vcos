const fs = require('fs');
let code = fs.readFileSync('app/(app)/embedded-analytics/page.tsx', 'utf8');

// Fix the early return pattern - use a function that returns JSX
const oldCode = `  };\r\n\r\n  const content = (\r\n    <div className="space-y-6">`;

const newCode = `  };\r\n\r\n  const renderContent = () => (\r\n    <div className="space-y-6">`;

if (code.includes(oldCode)) {
  code = code.replace(oldCode, newCode);
  
  // Also fix the closing - change `return content;` to `return renderContent();`
  const oldClose = `);\r\n  return content;\r\n}\r`;
  const newClose = `);\r\n  return renderContent();\r\n}\r`;
  
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