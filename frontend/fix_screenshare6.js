const fs = require('fs');
let code = fs.readFileSync('components/collaboration/ScreenShare.tsx', 'utf8');

// Replace the ternary with if/else
const oldBlock = `  const content = isSharing && stream ? (
    <div className={classNames(
      "relative bg-black rounded-lg border border-line overflow-hidden transition-all duration-300",
      isMinimized ? "w-48 h-27" : "w-full h-full",
      className
    )}>`;

const newBlock = `  let content = null;
  if (isSharing && stream) {
    content = (
    <div className={classNames(
      "relative bg-black rounded-lg border border-line overflow-hidden transition-all duration-300",
      isMinimized ? "w-48 h-27" : "w-full h-full",
      className
    )}>`;

if (code.includes(oldBlock)) {
  code = code.replace(oldBlock, newBlock);
  
  // Also fix the closing
  const oldClose = `    );\n  return content;\n}`;
  const newClose = `    );\n  }\n  return content;\n}`;
  
  if (code.includes(oldClose)) {
    code = code.replace(oldClose, newClose);
    fs.writeFileSync('components/collaboration/ScreenShare.tsx', code);
    console.log('Fixed ScreenShare.tsx with if/else');
  } else {
    console.log('Close pattern not found');
  }
} else {
  console.log('Block not found');
}