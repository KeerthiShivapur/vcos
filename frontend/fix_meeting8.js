const fs = require('fs');
let code = fs.readFileSync('app/(app)/meetings/[meetingId]/page.tsx', 'utf8');

// Fix the renderContent pattern - replace with direct return
const oldCode = `  const renderContent = () => (
    <div className="max-w-7xl mx-auto space-y-6 p-4">`;

const newCode = `  return (
    <div className="max-w-7xl mx-auto space-y-6 p-4">`;

if (code.includes(oldCode)) {
  code = code.replace(oldCode, newCode);
  
  // Also fix the closing - change `return renderContent();` to just close the return
  const oldClose = `);
  return renderContent();
  };
}`;

const newClose = `);
  };
}
`;

if (code.includes(oldClose)) {
  code = code.replace(oldClose, newClose);
  fs.writeFileSync('app/(app)/meetings/[meetingId]/page.tsx', code);
  console.log('Fixed meeting page - inlined return');
} else {
  console.log('Close pattern not found');
}