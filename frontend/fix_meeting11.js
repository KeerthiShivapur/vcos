const fs = require('fs');
let code = fs.readFileSync('app/(app)/meetings/new/page.tsx', 'utf8');

// Fix the renderContent pattern - replace with direct return
const oldCode = '  );\n\n  const renderContent = () => (\n    <div className={cn("max-w-4xl mx-auto space-y-6 p-4", className)}>';

const newCode = '  );\n\n  return (\n    <div className={cn("max-w-4xl mx-auto space-y-6 p-4", className)}>';

if (code.includes(oldCode)) {
  code = code.replace(oldCode, newCode);
  
  // Also fix the closing - change `return renderContent();` to just close the return
  const oldClose = ');\n  return renderContent();\n}\n';
  const newClose = ');\n}\n';
  
  if (code.includes(oldClose)) {
    code = code.replace(oldClose, newClose);
    fs.writeFileSync('app/(app)/meetings/new/page.tsx', code);
    console.log('Fixed new meeting page - inlined return');
  } else {
    console.log('Close pattern not found');
  }
} else {
  console.log('Old code not found');
}