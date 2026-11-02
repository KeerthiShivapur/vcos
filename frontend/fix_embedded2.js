const fs = require('fs');
let code = fs.readFileSync('app/(app)/embedded-analytics/page.tsx', 'utf8');

// Fix the early return pattern - assign JSX to variable
const oldCode = `  const getModeLabel = (mode: string) => {
    switch (mode) {
      case "iframe": return "Iframe";
      case "web_component": return "Web Component";
      case "javascript_sdk": return "JavaScript SDK";
      default: return mode;
    }
  };

  return (`;

const newCode = `  const getModeLabel = (mode: string) => {
    switch (mode) {
      case "iframe": return "Iframe";
      case "web_component": return "Web Component";
      case "javascript_sdk": return "JavaScript SDK";
      default: return mode;
    }
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
    fs.writeFileSync('app/(app)/embedded-analytics/page.tsx', code);
    console.log('Fixed embedded-analytics page 2');
  } else {
    console.log('Close pattern not found');
  }
} else {
  console.log('Pattern not found');
}