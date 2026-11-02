const fs = require('fs');
let code = fs.readFileSync('components/collaboration/ScreenShare.tsx', 'utf8');

// Replace the early return + return pattern with a ternary
const oldPattern = `if (!isSharing && !stream) return null;

  return (
    <div className={classNames(
      "relative bg-black rounded-lg border border-line overflow-hidden transition-all duration-300",
      isMinimized ? "w-48 h-27" : "w-full h-full",
      className
    )}>`;

const newPattern = `return isSharing && stream ? (
    <div className={classNames(
      "relative bg-black rounded-lg border border-line overflow-hidden transition-all duration-300",
      isMinimized ? "w-48 h-27" : "w-full h-full",
      className
    )}>`;

if (code.includes(oldPattern)) {
  code = code.replace(oldPattern, newPattern);
  fs.writeFileSync('components/collaboration/ScreenShare.tsx', code);
  console.log('Fixed ScreenShare.tsx - replaced early return with ternary');
} else {
  console.log('Pattern not found');
  // Try finding where the return starts
  const idx = code.indexOf('return (');
  if (idx > -1) {
    console.log('Found return at:', idx);
    console.log('Context:', code.substring(idx - 50, idx + 100));
  }
}