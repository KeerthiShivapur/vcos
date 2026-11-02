const fs = require('fs');
let code = fs.readFileSync('components/collaboration/ScreenShare.tsx', 'utf8');

// Fix the ternary - add : null before the closing );
const oldLine = `  );
}
`;

// Find the correct one (the one right before "// Main Screen Share Button Component")
const idx = code.indexOf('  );\n}\n\n// Main Screen Share Button Component');
if (idx > -1) {
  const before = code.substring(0, idx + 2); // up to and including "  );"
  const after = code.substring(idx + 2); // rest starting with "}\n\n// Main..."
  code = before + ' : null' + after;
  fs.writeFileSync('components/collaboration/ScreenShare.tsx', code);
  console.log('Fixed ScreenShare.tsx ternary');
} else {
  console.log('Pattern not found');
}