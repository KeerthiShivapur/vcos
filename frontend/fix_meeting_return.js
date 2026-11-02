const fs = require('fs');
let code = fs.readFileSync('app/(app)/meetings/[meetingId]/page.tsx', 'utf8');

// Fix the return statement - add comment before return
const oldCode = `  );
  return (`;
const newCode = `  );
  // Render the main JSX
  return (`;

if (code.includes(oldCode)) {
  code = code.replace(oldCode, newCode);
  fs.writeFileSync('app/(app)/meetings/[meetingId]/page.tsx', code);
  console.log('Fixed meeting page - added comment before return');
} else {
  console.log('Old code not found');
}