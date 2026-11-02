const fs = require('fs');
let code = fs.readFileSync('app/(app)/meetings/new/page.tsx', 'utf8');

// Fix the return statement - remove extra };
const oldCode = `  };\n\n  return (`;
const newCode = `\n  return (`;

if (code.includes(oldCode)) {
  code = code.replace(oldCode, newCode);
  fs.writeFileSync('app/(app)/meetings/new/page.tsx', code);
  console.log('Fixed new meeting page - removed extra } before return');
} else {
  console.log('Old code not found');
}