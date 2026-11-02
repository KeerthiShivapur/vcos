const fs = require('fs');
let code = fs.readFileSync('components/collaboration/ScreenShare.tsx', 'utf8');

// Replace the ternary return with variable assignment
const oldReturn = `return isSharing && stream ? (
    <div className={classNames(
      "relative bg-black rounded-lg border border-line overflow-hidden transition-all duration-300",
      isMinimized ? "w-48 h-27" : "w-full h-full",
      className
    )}>`;

const newReturn = `const content = isSharing && stream ? (
    <div className={classNames(
      "relative bg-black rounded-lg border border-line overflow-hidden transition-all duration-300",
      isMinimized ? "w-48 h-27" : "w-full h-full",
      className
    )}>`;

if (code.includes(oldReturn)) {
  code = code.replace(oldReturn, newReturn);
  
  // Also need to change the closing from `) : null;` to `); return content;`
  const oldClose = `) : null;
}
`;
  const newClose = `);
  return content;
}
`;
  
  if (code.includes(oldClose)) {
    code = code.replace(oldClose, newClose);
    fs.writeFileSync('components/collaboration/ScreenShare.tsx', code);
    console.log('Fixed ScreenShare.tsx - assigned JSX to variable');
  } else {
    console.log('Close pattern not found');
  }
} else {
  console.log('Return pattern not found');
}