const fs = require('fs');
let code = fs.readFileSync('components/collaboration/ScreenShare.tsx', 'utf8');

// Replace the if/else block with direct return
const oldBlock = `  let content = null;
  if (isSharing && stream) {
    content = (
    <div className={classNames(
      "relative bg-black rounded-lg border border-line overflow-hidden transition-all duration-300",
      isMinimized ? "w-48 h-27" : "w-full h-full",
      className
    )}>`;

const newBlock = `  if (!isSharing || !stream) return null;

  return (
    <div className={classNames(
      "relative bg-black rounded-lg border border-line overflow-hidden transition-all duration-300",
      isMinimized ? "w-48 h-27" : "w-full h-full",
      className
    )}>`;

if (code.includes(oldBlock)) {
  code = code.replace(oldBlock, newBlock);
  
  // Fix the closing
  const oldClose = `    );\n  }\n  return content;\n}`;
  const newClose = `    );\n}`;
  
  if (code.includes(oldClose)) {
    code = code.replace(oldClose, newClose);
    fs.writeFileSync('components/collaboration/ScreenShare.tsx', code);
    console.log('Fixed ScreenShare.tsx with direct return');
  } else {
    console.log('Close pattern not found');
  }
} else {
  console.log('Block not found');
}