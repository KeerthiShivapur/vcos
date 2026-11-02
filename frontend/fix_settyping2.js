const fs = require('fs');
let code = fs.readFileSync('hooks/useComments.ts', 'utf8');

// Fix the setTyping useCallback - rewrite with explicit returns
const oldCode = `const setTyping = useCallback((userId: string, isTyping: boolean) => {
    if (isTyping) {
      setTypingUsers(prev => new Set([...prev, userId]));
      // Auto-stop after 3 seconds
      const timeout = setTimeout(() => {
        setTypingUsers(prev => {
          const next = new Set(prev);
          next.delete(userId);
          return next;
        });
        typingTimeoutRef.current.delete(userId);
      }, 3000);
      typingTimeoutRef.current.set(userId, timeout);
    } else {
      setTypingUsers(prev => {
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

if (code.includes(oldCode)) {
  code = code.replace(oldCode, newCode);
  fs.writeFileSync('hooks/useComments.ts', code);
  console.log('Fixed useComments.ts setTyping with function syntax');
} else {
  console.log('Old code not found');
}