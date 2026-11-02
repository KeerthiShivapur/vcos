const fs = require('fs');
let code = fs.readFileSync('hooks/useComments.ts', 'utf8');

// Use regex to find and replace the comment_reaction case
// Match from "case 'comment_reaction':" to the closing "break;"
const regex = /case 'comment_reaction':[\s\S]*?break;/;

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

const newCode = code.replace(regex, newCase);

if (newCode !== code) {
  fs.writeFileSync('hooks/useComments.ts', newCode);
  console.log('Fixed useComments.ts');
} else {
  console.log('No match found');
}