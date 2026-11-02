const fs = require('fs');
let code = fs.readFileSync('components/collaboration/ScreenShare.tsx', 'utf8');
const lines = code.split('\n');

// Find line 44 (index 43) - "  return isSharing && stream ? ("
if (lines[43].includes('return isSharing && stream ? (')) {
  // Replace line 44 with variable assignment
  lines[43] = '  const content = isSharing && stream ? (';
  console.log('Fixed line 44');
}

// Find line 126 (index 125) - "   : null);"
if (lines[125].includes(': null);')) {
  // Replace with closing and return
  lines[125] = '    );';
  lines.splice(126, 0, '  return content;');
  console.log('Fixed line 126');
}

fs.writeFileSync('components/collaboration/ScreenShare.tsx', lines.join('\n'));
console.log('Fixed ScreenShare.tsx');