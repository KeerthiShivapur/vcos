const fs = require('fs');
let code = fs.readFileSync('hooks/useComments.ts', 'utf8');

// Fix the setTyping useCallback - add proper dependencies
const oldCode = `  }, []);\n\n  return {`;
const newCode = `  }, [setTypingUsers, typingTimeoutRef]);\n\n  return {`;

if (code.includes(oldCode)) {
  code = code.replace(oldCode, newCode);
  fs.writeFileSync('hooks/useComments.ts', code);
  console.log('Fixed useComments.ts setTyping dependencies');
} else {
  console.log('Old code not found');
}