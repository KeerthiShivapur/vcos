const fs = require('fs');
let code = fs.readFileSync('app/(app)/docs/embedded-analytics/page.tsx', 'utf8');

// Fix the early return pattern - assign JSX to variable
const oldCode = `  const navigate = (id: string) => {
    setActiveSection(id);
    if (window.innerWidth < 1024) setSidebarOpen(false);
  };

  return (`;

const newCode = `  const navigate = (id: string) => {
    setActiveSection(id);
    if (window.innerWidth < 1024) setSidebarOpen(false);
  };

  const content = (`;

if (code.includes(oldCode)) {
  code = code.replace(oldCode, newCode);
  
  // Also fix the closing - change `); }` to `); return content; }`
  const oldClose = `);
}
`;
  const newClose = `);
  return content;
}
`;
  
  if (code.includes(oldClose)) {
    code = code.replace(oldClose, newClose);
    fs.writeFileSync('app/(app)/docs/embedded-analytics/page.tsx', code);
    console.log('Fixed embedded-analytics page');
  } else {
    console.log('Close pattern not found');
  }
} else {
  console.log('Pattern not found');
}