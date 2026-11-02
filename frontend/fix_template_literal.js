const fs = require('fs');
const code = fs.readFileSync('components/collaboration/CommentThread.tsx', 'utf8');
const fixed = code.replace(
  '<div className={`flex flex-col h-full bg-canvas border border-line rounded-xl ${className || \'\'}`}>',
  '<div className={`flex flex-col h-full bg-canvas border border-line rounded-xl ${className || \'\'}`}>'
);
fs.writeFileSync('components/collaboration/CommentThread.tsx', fixed);
console.log('Fixed!');