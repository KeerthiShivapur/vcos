const fs = require('fs');
let code = fs.readFileSync('components/collaboration/ScreenShare.tsx', 'utf8');

// Find the ternary return and replace with variable assignment
// Pattern: return isSharing && stream ? ( ... ) : null;
const regex = /return isSharing && stream \? \(\s*<div className=\{classNames\([\s\S]*?\)\s*:\s*null\);/;

const match = code.match(regex);
if (match) {
  console.log('Found match at index:', match.index);
  console.log('Match length:', match[0].length);
  
  const replacement = `const content = isSharing && stream ? (
    <div className={classNames(
      "relative bg-black rounded-lg border border-line overflow-hidden transition-all duration-300",
      isMinimized ? "w-48 h-27" : "w-full h-full",
      className
    )}>`;
  
  const newCode = code.replace(regex, replacement);
  
  if (newCode !== code) {
    // Now replace the closing
    const closeRegex = /\)\s*:\s*null\);/;
    const finalCode = newCode.replace(closeRegex, `);\n  return content;\n`);
    
    fs.writeFileSync('components/collaboration/ScreenShare.tsx', finalCode);
    console.log('Fixed ScreenShare.tsx - assigned JSX to variable');
  } else {
    console.log('Could not replace ternary');
  }
} else {
  console.log('Ternary pattern not found');
}