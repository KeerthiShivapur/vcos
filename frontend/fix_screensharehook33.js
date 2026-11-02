const fs = require('fs');
let code = fs.readFileSync('hooks/useScreenShare.ts', 'utf8');

// Fix the return statement - expand the spread operator
const oldCode = `    return {
      ...state,
      startScreenShare,
      stopScreenShare,
      toggleScreenShare,
      replaceTrack,
    };
  };
}`;

const newCode = `    return {
      isSharing: state.isSharing,
      stream: state.stream,
      error: state.error,
      tracks: state.tracks,
      startScreenShare,
      stopScreenShare,
      toggleScreenShare,
      replaceTrack,
    };
  };
}`;

if (code.includes(oldCode)) {
  code = code.replace(oldCode, newCode);
  fs.writeFileSync('hooks/useScreenShare.ts', code);
  console.log('Fixed useScreenShare.ts - expanded return statement');
} else {
  console.log('Old code not found');
}