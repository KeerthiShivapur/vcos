const fs = require('fs');
let code = fs.readFileSync('app/(app)/embedded-analytics/page.tsx', 'utf8');

// Fix the early return pattern - use a function that returns JSX
const oldCode = `  };

  const content = (
    <div className="space-y-6">`;

const newCode = `  };

  const renderContent = () => (
    <div className="space-y-6">`;

if (code.includes(oldCode)) {
  code = code.replace(oldCode, newCode);
  
  // Also fix the closing - change `return content;` to `return renderContent();`
  const oldClose = `);
  return content;
}
`;
  const newClose = `);
  return renderContent();
}
`;
  
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