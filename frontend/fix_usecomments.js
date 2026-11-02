const fs = require('fs');
let code = fs.readFileSync('hooks/useComments.ts', 'utf8');

// Find and replace the comment_reaction case
const oldCase = `case 'comment_reaction':
        setThreads(prev => prev.map(t => {
          if (t.id === message.payload.threadId) {
            const updatedComments = t.comments.map(c => {
                if (c.id === message.payload.commentId) {
                  const reactions = { ...c.reactions };
                  const users = reactions[message.payload.emoji] || [];
                  if (message.payload.added) {
                    reactions[message.payload.emoji] = [...users, message.payload.userId];
                  } else {
                    reactions[message.payload.emoji] = users.filter((id: string) => id !== message.payload.userId);
                  }
                  return { ...c, reactions }
                }
                return c;
              });
            const updatedThread = Object.assign({}, t, { comments: updatedComments });
            return updatedThread;
          }
          return t;
        }));`;

const newCase = `case 'comment_reaction':
        setThreads(prev => prev.map(t => {
          if (t.id !== message.payload.threadId) return t;
          
          const updatedComments = t.comments.map(c => {
            if (c.id === message.payload.commentId) {
              const reactions = { ...c.reactions };
              const users = reactions[message.payload.emoji] || [];
              if (message.payload.added) {
                reactions[message.payload.emoji] = [...users, message.payload.userId];
              } else {
                reactions[message.payload.emoji] = users.filter((id: string) => id !== message.payload.userId);
              }
              return { ...c, reactions }
            }
            return c;
          });
          return Object.assign({}, t, { comments: updatedComments });
        }));`;

if (code.includes(oldCase)) {
  code = code.replace(oldCase, newCase);
  fs.writeFileSync('hooks/useComments.ts', code);
  console.log('Fixed useComments.ts');
} else {
  console.log('Old case not found');
}