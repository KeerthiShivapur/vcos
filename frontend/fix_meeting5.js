const fs = require('fs');
let code = fs.readFileSync('app/(app)/meetings/[meetingId]/page.tsx', 'utf8');

// Fix the early return pattern - use a function that returns JSX
const oldCode = `  );\n\n  const content = (\n    <div className="max-w-7xl mx-auto space-y-6 p-4">`;

const newCode = `  );\n\n  const renderContent = () => (\n    <div className="max-w-7xl mx-auto space-y-6 p-4">`;

if (code.includes(oldCode)) {
  code = code.replace(oldCode, newCode);
  
  // Also fix the closing - change `return content;` to `return renderContent();`
  const oldClose = `);\n  return content;\n}\n`;
  const newClose = `);\n  return renderContent();\n}\n`;
  
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