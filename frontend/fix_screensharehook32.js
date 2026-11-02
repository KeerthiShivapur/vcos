const fs = require('fs');
let code = fs.readFileSync('hooks/useScreenShare.ts', 'utf8');

// Fix the useEffect cleanup - missing closing brace
const oldCode = `useEffect(() => {
    return () => {
      if (state.isSharing) {
        stopScreenShare();
      }
    }, [state.isSharing]);`;

const newCode = `useEffect(() => {
    return () => {
      if (state.isSharing) {
        stopScreenShare();
      }
    };
  }, [state.isSharing]);`;

if (code.includes(oldCode)) {
  code = code.replace(oldCode, newCode);
  fs.writeFileSync('hooks/useScreenShare.ts', code);
  console.log('Fixed useScreenShare.ts - useEffect cleanup');
} else {
  console.log('Old code not found');
}