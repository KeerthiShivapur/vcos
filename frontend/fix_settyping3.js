const fs = require('fs');
let code = fs.readFileSync('hooks/useComments.ts', 'utf8');

// Find the setTyping useCallback using regex
const regex = /const setTyping = useCallback\(\(userId: string, isTyping: boolean\) => \{[\s\S]*?\}, \[setTypingUsers, typingTimeoutRef\]\);/;

const match = code.match(regex);
if (match) {
  console.log('Found match at index:', match.index);
  console.log('Match length:', match[0].length);
  
  const newCode = `const setTyping = useCallback((userId: string, isTyping: boolean) => {
    if (isTyping) {
      setTypingUsers(function(prev) { return new Set([...prev, userId]); });
      // Auto-stop after 3 seconds
      const timeout = setTimeout(function() {
        setTypingUsers(function(prev) {
          const next = new Set(prev);
          next.delete(userId);
          return next;
        });
        typingTimeoutRef.current.delete(userId);
      }, 3000);
      typingTimeoutRef.current.set(userId, timeout);
    } else {
      setTypingUsers(function(prev) {
        const next = new Set(prev);
        next.delete(userId);
        return next;
      });
      const timeout = typingTimeoutRef.current.get(userId);
      if (timeout) {
        clearTimeout(timeout);
        typingTimeoutRef.current.delete(userId);
      }
    }
  }, [setTypingUsers, typingTimeoutRef]);`;

  const newFullCode = code.replace(regex, newCode);
  
  if (newFullCode !== code) {
    fs.writeFileSync('hooks/useComments.ts', newFullCode);
    console.log('Fixed useComments.ts setTyping with function syntax');
  } else {
    console.log('Replacement did not change code');
  }
} else {
  console.log('Pattern not found');
}