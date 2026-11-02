const fs = require('fs');
const filePath = 'components/collaboration/CommentThread.tsx';
const code = fs.readFileSync('components/collaboration/CommentThread.tsx', 'utf8');

// Remove the extra closing brace
const fixed = code.replace(
  '  }\n}\n\nfunction generateColor(id: string): string {',
  '  }\n\nfunction generateColor(id: string): string {'
);

fs.writeFileSync('components/collaboration/CommentThread.tsx', fixed);
console.log('Fixed!');